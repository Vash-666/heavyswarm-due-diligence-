#!/usr/bin/env python3
"""JWT Secret Rotation Script for HeavySwarm.

This script generates a new JWT secret key and provides instructions
for updating the production environment.

Usage:
    python scripts/rotate_jwt_secret.py

Safety:
    - Generates cryptographically secure random key
    - Provides rollback instructions
    - Validates new key format
"""

import secrets
import sys
from datetime import datetime
from pathlib import Path


def generate_secret() -> str:
    """Generate a cryptographically secure JWT secret.
    
    Returns:
        A URL-safe base64-encoded 32-byte secret
    """
    # Generate 32 bytes (256 bits) of randomness
    return secrets.token_urlsafe(32)


def validate_secret(secret: str) -> bool:
    """Validate the generated secret.
    
    Args:
        secret: The secret to validate
        
    Returns:
        True if valid, False otherwise
    """
    # Check minimum length (32 bytes = ~43 chars in base64)
    if len(secret) < 32:
        print("ERROR: Secret is too short")
        return False
    
    # Check for common weak patterns
    weak_patterns = ["password", "secret", "123", "admin", "test"]
    if any(pattern in secret.lower() for pattern in weak_patterns):
        print("ERROR: Secret contains weak pattern")
        return False
    
    return True


def print_rotation_instructions(new_secret: str) -> None:
    """Print rotation instructions.
    
    Args:
        new_secret: The new secret to use
    """
    print("=" * 70)
    print("JWT SECRET ROTATION")
    print("=" * 70)
    print(f"\nGenerated at: {datetime.utcnow().isoformat()} UTC")
    print(f"\nNew Secret: {new_secret}")
    print("\n" + "=" * 70)
    print("ROTATION PROCEDURE")
    print("=" * 70)
    print("""
1. BACKUP CURRENT SECRET
   - Save the current SECRET_KEY value securely
   - Store in password manager or encrypted backup

2. UPDATE ENVIRONMENT
   - Set the new SECRET_KEY in your environment:
   
     export SECRET_KEY="{new_secret}"
   
   - Or update your .env file:
   
     SECRET_KEY={new_secret}

3. ROLLING RESTART
   - Restart API instances one at a time
   - Verify each instance passes health checks
   - Monitor error rates during restart

4. VERIFY
   - Test authentication with new tokens
   - Verify existing sessions still work (during transition)
   - Check logs for any errors

5. CLEANUP
   - Remove old secret from environment after 30 minutes
   - (All old tokens will have expired by then)
""".format(new_secret=new_secret))
    
    print("=" * 70)
    print("ROLLBACK PROCEDURE (if needed)")
    print("=" * 70)
    print("""
If issues occur during rotation:

1. Restore the previous SECRET_KEY
2. Restart all API instances
3. Users may need to re-authenticate
4. Investigate root cause
""")
    
    print("=" * 70)
    print("IMPORTANT NOTES")
    print("=" * 70)
    print("""
- Keep the new secret secure - never commit to git
- Rotate during low-traffic period
- Have rollback plan ready
- Monitor authentication errors during rotation
- Old tokens expire after 30 minutes (default)
""")


def main() -> int:
    """Main entry point.
    
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    print("HeavySwarm JWT Secret Rotation Tool\n")
    
    # Generate new secret
    new_secret = generate_secret()
    
    # Validate
    if not validate_secret(new_secret):
        print("ERROR: Generated secret failed validation")
        return 1
    
    # Print instructions
    print_rotation_instructions(new_secret)
    
    # Save to file for convenience (with warning)
    backup_dir = Path(".secrets_backup")
    backup_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"jwt_secret_{timestamp}.txt"
    
    with open(backup_file, "w") as f:
        f.write(f"# JWT Secret generated at {datetime.utcnow().isoformat()} UTC\n")
        f.write(f"# WARNING: Keep this file secure and delete after rotation\n")
        f.write(f"SECRET_KEY={new_secret}\n")
    
    print(f"\nSecret also saved to: {backup_file}")
    print("WARNING: Delete this file after successful rotation!")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
