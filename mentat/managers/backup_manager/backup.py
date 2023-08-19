import os
import shutil
from typing import Optional
from termcolor import cprint


class CodeBackupManager:
    def __init__(self, backup_dir: Optional[str] = ".mentat_backups"):
        self.backup_dir = backup_dir

        if not self.backup_dir:
            raise ValueError("Backup directory cannot be None or empty.")

        try:
            os.makedirs(self.backup_dir, exist_ok=True)
        except OSError as e:
            cprint(
                f"Error occurred while creating backup directory '{self.backup_dir}': {str(e)}",
                color="red",
            )
            raise
        except Exception as e:
            cprint(
                f"An unexpected error occurred while creating backup directory: {str(e)}",
                color="red",
            )
            raise

    def _get_backup_path(self, file_path: str) -> str:
        relative_path = os.path.relpath(file_path)
        if os.path.sep in relative_path:
            parent_folder, file_name = os.path.split(relative_path)
            backup_folder = os.path.join(self.backup_dir, parent_folder)
            return os.path.join(backup_folder, file_name + ".backup")
        else:
            return os.path.join(
                self.backup_dir, os.path.basename(file_path) + ".backup"
            )

    def backup_files(self, code_file_manager):
        cprint("Creating backups...", color="yellow")

        for file_path in code_file_manager.get_all_file_paths():
            backup_file_path = self._get_backup_path(file_path)

            if not os.path.exists(backup_file_path):
                try:
                    os.makedirs(os.path.dirname(backup_file_path), exist_ok=True)
                    shutil.copy2(file_path, backup_file_path)
                    cprint(
                        f"Backup created successfully for the file {file_path}.",
                        color="green",
                    )
                except PermissionError:
                    cprint(
                        f"Permission denied when trying to create backup for {file_path}.",
                        color="red",
                    )
                except Exception as e:
                    cprint(
                        f"An error occurred while trying to create backup for {file_path}: {str(e)}.",
                        color="red",
                    )

        cprint("Backup process exited...", color="green")

    def restore_file(self, original_file_path: str) -> bool:
        backup_file_path = self._get_backup_path(original_file_path)

        try:
            shutil.copy2(backup_file_path, original_file_path)
            cprint(
                f"File {original_file_path} restored successfully from backup.",
                color="green",
            )
            return True
        except PermissionError:
            cprint(
                f"Permission denied when trying to restore {original_file_path}.",
                color="red",
            )
        except Exception as e:
            cprint(
                f"An error occurred while trying to restore {original_file_path}: {str(e)}.",
                color="red",
            )

        return True
