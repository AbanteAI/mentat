from pathlib import Path
from uuid import uuid4

import attr

from mentat.code_feature import get_consolidated_feature_refs
from mentat.python_client.client import PythonClient
from mentat.sampler.sample import Sample
from mentat.sampler.utils import setup_repo
from mentat.session_context import SESSION_CONTEXT


async def add_context(sample, extra_tokens: int = 5000) -> Sample:
    """Return a duplicate sample with extra (auto-context generated) context."""
    # Setup mentat CodeContext with included_files
    repo = setup_repo(
        url=sample.repo,
        commit=sample.merge_base,
        diff_merge_base=sample.diff_merge_base,
        diff_active=sample.diff_active,
    )
    cwd = Path(repo.working_dir)
    paths = list[Path]()
    for a in sample.context:
        paths.append(Path(a))
    python_client = PythonClient(cwd=cwd, paths=paths)
    await python_client.startup()

    # Use auto-context to add extra tokens, then copy the resulting features
    ctx = SESSION_CONTEXT.get()
    ctx.config.auto_context_tokens = extra_tokens
    _ = await ctx.code_context.get_code_message(
        prompt_tokens=0, prompt=sample.message_prompt
    )
    included_features = list(
        f for fs in ctx.code_context.include_files.values() for f in fs
    )
    auto_features = ctx.code_context.auto_features
    all_features = get_consolidated_feature_refs(included_features + auto_features)
    await python_client.shutdown()

    new_sample = Sample(**attr.asdict(sample))
    new_sample.context = [str(f) for f in all_features]
    new_sample.id = uuid4().hex
    new_sample.title = f"{sample.title} [ADD {extra_tokens} CONTEXT]"
    return new_sample
