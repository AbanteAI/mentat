from pathlib import Path

import pytest

from mentat.context_tree import ContextNode, DirectoryNode, FileNode


@pytest.fixture
def root(temp_testbed) -> ContextNode:
    root_path = Path(temp_testbed)
    root = ContextNode(root_path)
    
    # Add testbed children manually
    mf_calculator = ContextNode(Path("multifile_calculator"), root)
    root.children[Path(mf_calculator.path.name)] = mf_calculator
    
    init = ContextNode(Path(mf_calculator.path / "__init__.py"), mf_calculator)
    calculator = ContextNode(Path(mf_calculator.path / "calculator.py"), mf_calculator)
    operations = ContextNode(Path(mf_calculator.path / "operations.py"), mf_calculator)
    mf_calculator.children[Path(init.path.name)] = init
    mf_calculator.children[Path(calculator.path.name)] = calculator
    mf_calculator.children[Path(operations.path.name)] = operations
    return root


class TestContextNode:
    def test_context_node_init(self, temp_testbed, root: ContextNode):
        assert root.path == Path(temp_testbed)
        assert root.parent is None
        assert isinstance(root.children, dict)
        assert (not s for s in root.node_settings.__dict__.values())
        

    def test_context_node_navigation(self, root: ContextNode):
        # Test navigation
        operations = root.children[Path('multifile_calculator')][Path('operations.py')]
        assert operations.root() == root
        assert operations.relative_path() == Path("multifile_calculator/operations.py")
        # Test __getitem__ (works with string, relative Path or absolute Path)
        assert root['multifile_calculator/operations.py'] == operations
        assert root[Path('multifile_calculator/operations.py')] == operations
        assert root[Path('multifile_calculator/operations.py').resolve()] == operations
        with pytest.raises(KeyError):
            root['missing_file']
        # Test iter_nodes: return subtree depth-first
        expected = [
            "testbed", 
                "multifile_calculator", 
                    "__init__.py", 
                    "calculator.py", 
                    "operations.py"
        ]
        assert [n.path.name for n in root.iter_nodes()] == expected
        assert [n.path.name for n in root.iter_nodes(include_files=False)] == expected[:2]
        assert [n.path.name for n in root.iter_nodes(include_dirs=False)] == expected[2:]


    def test_context_node_message_generation(self, root: ContextNode):
        def _included_files():
            return [n.path.name for n in root.iter_nodes() if n.node_settings.include]
        assert not _included_files()
        root['multifile_calculator'].update_settings({'include': True}, recursive=False)
        assert _included_files() == ['multifile_calculator']
        root['multifile_calculator'].update_settings({'include': True}, recursive=True)
        assert _included_files() == ['multifile_calculator', '__init__.py', 'calculator.py', 'operations.py']

        with pytest.raises(NotImplementedError):
            root.display_context()
        with pytest.raises(NotImplementedError):
            root.get_code_message()


class TestDirectoryNode:
    def test_directory_node_refresh(self, temp_testbed):
        root = DirectoryNode(Path(temp_testbed))
        # Calls refresh automatically
        expected = [
            'testbed', 
                '.gitignore', 
                '__init__.py', 
                'multifile_calculator', 
                    '__init__.py', 
                    'calculator.py',
                    'operations.py', 
                'scripts', 
                    'calculator.py', 
                    'echo.py', 
                    'graph_class.py', 
        ]
        assert [n.path.name for n in root.iter_nodes()] == expected

        # New untracked files show up in context
        untracked_file = Path(temp_testbed, "untracked_file.py")
        untracked_file.write_text("print('hello')")
        root.refresh()
        assert root[untracked_file].path == untracked_file.resolve()

        # New git-ignored files do not show up in context...
        ignored_file = Path(temp_testbed, "ignored_file.py")
        ignored_file.write_text("print('hello')")
        with open(Path(temp_testbed, ".gitignore"), "a") as f:
            f.write("\nignored_file.py")
        root.refresh()
        with pytest.raises(KeyError):
            root[ignored_file]
        # ...but if added manually, refresh leaves them alone.
        root.children[Path("ignored_file.py")] = FileNode(ignored_file, root)
        root[ignored_file].update_settings({'include': True})
        root.refresh()
        assert root[ignored_file].path == ignored_file.resolve()

    def test_directory_node_display_generation(self, temp_testbed, capfd):
        # If no paths selected, just print directory name
        root = DirectoryNode(Path(temp_testbed))
        root.display_context()
        out, err = capfd.readouterr()
        assert out.splitlines() == []

        root['scripts'].update_settings({'include': True}, recursive=True)
        root.refresh()
        root.display_context()
        out, err = capfd.readouterr()
        assert out.splitlines() == [
            "└── scripts",
            "    ├── calculator.py",
            "    ├── echo.py",
            "    └── graph_class.py",
        ]
        
        code_message = root.get_code_message(recursive=True)
        assert code_message[:3] == [
            "./",
            "scripts/",
            "scripts/calculator.py"
        ]
        expected_calculator_length = len(root['scripts/calculator.py'].path.read_text().splitlines())
        echo_index = code_message.index("scripts/echo.py")
        assert len(code_message[3:echo_index]) == expected_calculator_length


@pytest.fixture
def mock_node_context(mocker):
    # When mentat.diff_context.annotate_file_message is called, just append second arg to first
    mock = mocker.patch("mentat.context_tree.file_node.annotate_file_message")
    def fake_annotate_file_message(x, y):
        return x + [_y.message for _y in y]
    mock.side_effect = fake_annotate_file_message
    # When get_code_map is called, return basic string
    mocker.patch("mentat.context_tree.file_node.get_code_map").return_value = "code_map"
    
    
class DummyDiffAnnotation:
    start: int
    length: int
    message: list[str]


class TestFileNode:
    def test_file_node_refresh(self, temp_testbed):
        # Content hash
        node = FileNode(Path(temp_testbed, "scripts/calculator.py"))
        initial_hash = node._hash
        with node.path.open("a") as f:
            f.write("print('hello')")
        node.refresh()
        assert node._hash != initial_hash

    def test_file_node_get_code_message(self, temp_testbed, mock_node_context):
        # Default case: not included
        node = FileNode(Path(temp_testbed, "scripts/calculator.py"))
        message = node.get_code_message()
        assert message == []

        # Include entire file
        node.update_settings({'include': True})
        message = node.get_code_message()
        assert len(message) == 1 + len(node.path.read_text().splitlines())

        # Include entire file *and* a diff
        node.update_settings({'diff': True})
        annot = DummyDiffAnnotation()
        annot.start = 0
        annot.length = 1
        annot.message = ['hello']
        node.set_diff_annotations([annot])
        message = node.get_code_message()
        assert len(message) == 1 + len(node.path.read_text().splitlines()) + 1
        assert message[-1] == ['hello']

        # Include only diff
        node.update_settings({'include': False})
        message = node.get_code_message()
        assert message == [
            '.',  # Filepath relative to root
            '0:1',  # Affected lines
            'hello',  # Content
        ]

        # Include 
        node.update_settings({'code_map': True})
        message = node.get_code_message()
        assert message[-1] == 'code_map'
