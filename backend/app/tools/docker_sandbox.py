import asyncio
import logging
import shutil
from pathlib import Path

from app.tools.sandbox import SandboxExecutor

logger = logging.getLogger(__name__)

# The image agents' commands run inside. Deliberately a plain language runtime with no build
# toolchain and no credentials of any kind.
SANDBOX_IMAGE = "python:3.12-slim"

WORKSPACE_MOUNT = "/workspace"


class DockerSandboxExecutor(SandboxExecutor):
    """Runs an agent's commands inside a throwaway container instead of on the host.

    The path restriction in SandboxExecutor keeps a *cooperative* agent inside its workspace,
    which is enough for a Coder writing files. It is not enough for anything that runs code -
    a command is free to ignore it entirely. This adds the boundary that actually holds:

      --network none      no egress, so a task cannot reach the internet, the model provider,
                          this host's other services, or the Docker socket
      --memory / --cpus   a runaway process cannot starve the host the console runs on
      --pids-limit        no fork bombs
      --read-only         the image is immutable; only the workspace mount is writable
      --cap-drop ALL      no capabilities
      no-new-privileges   setuid binaries cannot escalate
      --rm                nothing survives the command

    Falls back to the host executor when Docker is unavailable so development on a machine
    without it still works - but a run that needs real isolation must check `available()`
    rather than assuming it got a container.
    """

    def __init__(
        self,
        workspace_root: Path,
        *,
        image: str = SANDBOX_IMAGE,
        memory: str = "512m",
        cpus: str = "1.0",
        pids_limit: int = 128,
        network: str = "none",
    ):
        super().__init__(workspace_root)
        self.image = image
        self.memory = memory
        self.cpus = cpus
        self.pids_limit = pids_limit
        self.network = network

    @staticmethod
    def available() -> bool:
        return shutil.which("docker") is not None

    async def run_command(self, args: list[str], timeout: float = 30.0) -> dict:
        if not self.available():
            logger.warning("docker unavailable; running %s on the host instead", args[0])
            return await super().run_command(args, timeout=timeout)

        docker_args = [
            "docker", "run", "--rm",
            "--network", self.network,
            "--memory", self.memory,
            "--memory-swap", self.memory,  # equal to memory = no swap, so the cap is real
            "--cpus", self.cpus,
            "--pids-limit", str(self.pids_limit),
            "--read-only",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            # The workspace is the one writable place, plus a small tmpfs because too much
            # ordinary tooling refuses to run without a writable /tmp.
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "-v", f"{self.workspace_root.resolve()}:{WORKSPACE_MOUNT}:rw",
            "-w", WORKSPACE_MOUNT,
            "--user", "1000:1000",
            self.image,
            *args,
        ]

        proc = await asyncio.create_subprocess_exec(
            *docker_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise

        return {
            "returncode": proc.returncode,
            "stdout": stdout.decode(errors="replace"),
            "stderr": stderr.decode(errors="replace"),
            "sandboxed": True,
        }
