import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
PROJECT_DIR = BASE_DIR / "projects"

def build():
    failed = []
    for project in PROJECT_DIR.iterdir():
        if (project / "pyproject.toml").exists() and not project.name.startswith('.'):
            print(f"Building wheel for {project.name}...")
            try:
                subprocess.run(["poetry", "build-project"], cwd=project, check=True)
            except:
                failed.append(str(project.name))
            print("\n-----\n")
    if failed:
        print(f"Builds Failed:")
        for project in failed:
            print(f"- {project}")

if __name__ == "__main__":
    build()
