from pathlib import Path

try:  # copy .env.example to .env and fill it in; it is loaded here, before any other module reads the environment
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")  # an explicit path: works from any working directory
except ImportError:  # python-dotenv not installed: use real environment variables instead
    pass
