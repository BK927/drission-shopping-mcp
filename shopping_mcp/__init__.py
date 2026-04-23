from dotenv import load_dotenv

# Load .env as early as possible so module-level code (slot calculation,
# BrowserConfig.from_env, etc.) sees values set in the project's .env file.
load_dotenv()

__all__: list[str] = []
