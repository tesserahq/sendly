#!/usr/bin/env python3
import secrets
import base64
from pathlib import Path


def generate_credential_key():
    """Generate a secure random key for credential encryption."""
    # Generate 32 random bytes and encode them in base64
    key = base64.b64encode(secrets.token_bytes(32)).decode("utf-8")
    return key


def main():
    key = generate_credential_key()

    # Get the project root directory
    project_root = Path(__file__).parent.parent

    # Check if .env file exists
    env_file = project_root / ".env"
    env_exists = env_file.exists()

    print("\n=== Credential Master Key Generator ===\n")
    print(f"Generated key: {key}\n")

    if env_exists:
        print("Found existing .env file.")
        with open(env_file, "r") as f:
            content = f.read()

        if "CREDENTIAL_MASTER_KEY=" in content:
            print("\nWARNING: CREDENTIAL_MASTER_KEY already exists in .env file!")
            print("Please manually update the key if needed.")
        else:
            with open(env_file, "a") as f:
                f.write(f"\nCREDENTIAL_MASTER_KEY={key}\n")
            print("\nAdded CREDENTIAL_MASTER_KEY to .env file.")
    else:
        print("No .env file found. Creating one...")
        with open(env_file, "w") as f:
            f.write(f"CREDENTIAL_MASTER_KEY={key}\n")
        print("\nCreated .env file with CREDENTIAL_MASTER_KEY.")

    print("\n=== Next Steps ===")
    print("1. Make sure to keep this key secure and never commit it to version control")
    print(
        "2. If you're using Docker, make sure to pass this key as an environment variable"
    )
    print(
        "3. If you're deploying to production, set this key in your production environment\n"
    )


if __name__ == "__main__":
    main()
