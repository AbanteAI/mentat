import { exec } from "child_process";

const cmd = process.platform == "win32" ? "rmdir /s /q build" : "rm -rf build";

exec(cmd, (error) => {
  if (error) {
    console.error("Error:", error);
    process.exit(1);
  } else {
    console.log("Build folder deleted.");
  }
});
