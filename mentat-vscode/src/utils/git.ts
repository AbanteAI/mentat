import { exec } from "child_process";
import { promisify } from "util";

const aexec = promisify(exec);

async function getGitRoot(path: string): Promise<string> {
  try {
    const { stdout, stderr } = await aexec(`git -C ${path} rev-parse --show-toplevel`);

    if (stderr) {
      throw new Error(`Error: ${stderr}`);
    }

    return stdout.trim();
  } catch (error: any) {
    throw new Error(`Error: ${error.message}`);
  }
}

export { getGitRoot };
