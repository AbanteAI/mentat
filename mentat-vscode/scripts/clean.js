const { exec } = require("child_process");

if (process.platform === "win32") {
  exec("rmdir /s /q build", (error) => {
    if (error) console.error("Error:", error);
    else console.log("Build folder deleted.");
  });
} else {
  exec("rm -rf build", (error) => {
    if (error) console.error("Error:", error);
    else console.log("Build folder deleted.");
  });
}
