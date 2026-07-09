"""Security-related CLI commands."""
import logging
from pathlib import Path

from tokenade.core.crypto.encryptor import TokenadeEncryptor, encrypt_session, decrypt_session, load_key_from_file

logger = logging.getLogger("tokenade")


def cmd_encrypt(args):
    """Encrypt session file."""
    print("\n" + "=" * 80)
    print("TOKENADE - Encrypt Session")
    print("=" * 80)

    input_file = Path(args.input)
    if not input_file.exists():
        print(f"❌ Input file not found: {args.input}")
        raise SystemExit(1)

    if args.key_file:
        password = load_key_from_file(args.key_file)
        print(f"\n🔑 Loaded key from: {args.key_file}")
    elif args.password:
        password = args.password
    else:
        import getpass
        password = getpass.getpass("\n🔑 Enter password: ")
        confirm = getpass.getpass("🔑 Confirm password: ")
        if password != confirm:
            print("❌ Passwords don't match")
            raise SystemExit(1)

    output = args.output or str(input_file) + '.encrypted'

    try:
        print(f"\n📂 Input: {args.input}")
        print(f"📁 Output: {output}")

        result = encrypt_session(str(input_file), password, output)

        print("\n✅ Encrypted successfully")
        print(f"   Output: {result}")

        input_size = input_file.stat().st_size
        output_size = Path(result).stat().st_size
        print(f"   Size: {input_size} -> {output_size} bytes")

    except SystemExit:
        raise
    except Exception as e:
        logger.error(f"Encryption failed: {e}", exc_info=True)
        print("❌ Encryption failed — check input file is readable")
        raise SystemExit(1) from e


def cmd_decrypt(args):
    """Decrypt session file."""
    print("\n" + "=" * 80)
    print("TOKENADE - Decrypt Session")
    print("=" * 80)

    input_file = Path(args.input)
    if not input_file.exists():
        print(f"❌ Input file not found: {args.input}")
        raise SystemExit(1)

    if args.key_file:
        password = load_key_from_file(args.key_file)
        print(f"\n🔑 Loaded key from: {args.key_file}")
    elif args.password:
        password = args.password
    else:
        import getpass
        password = getpass.getpass("\n🔑 Enter password: ")

    output = args.output or str(input_file).replace('.encrypted', '')
    if output == str(input_file):
        output = str(input_file) + '.decrypted'

    try:
        print(f"\n📂 Input: {args.input}")
        print(f"📁 Output: {output}")

        result = decrypt_session(str(input_file), password, output)

        print("\n✅ Decrypted successfully")
        print(f"   Output: {result}")

        input_size = input_file.stat().st_size
        output_size = Path(result).stat().st_size
        print(f"   Size: {input_size} -> {output_size} bytes")

    except SystemExit:
        raise
    except ValueError as e:
        print("❌ Wrong password or corrupted file")
        logger.debug(f"Decryption error: {e}")
        raise SystemExit(1) from e
    except Exception as e:
        logger.error(f"Decryption failed: {e}", exc_info=True)
        print("❌ Decryption failed — verify password and file integrity")
        raise SystemExit(1) from e


def cmd_rekey(args):
    """Change encryption password."""
    print("\n" + "=" * 80)
    print("TOKENADE - Rekey Session")
    print("=" * 80)

    input_file = Path(args.input)
    if not input_file.exists():
        print(f"❌ Input file not found: {args.input}")
        raise SystemExit(1)

    if args.old_key_file:
        old_password = load_key_from_file(args.old_key_file)
        print(f"\n🔑 Loaded old key from: {args.old_key_file}")
    elif args.old_password:
        old_password = args.old_password
    else:
        import getpass
        old_password = getpass.getpass("\n🔑 Enter old password: ")

    if args.new_key_file:
        new_password = load_key_from_file(args.new_key_file)
        print(f"🔑 Loaded new key from: {args.new_key_file}")
    elif args.new_password:
        new_password = args.new_password
    else:
        import getpass
        new_password = getpass.getpass("\n🔑 Enter new password: ")
        confirm = getpass.getpass("🔑 Confirm new password: ")
        if new_password != confirm:
            print("❌ Passwords don't match")
            raise SystemExit(1)

    output = args.output or str(input_file)

    try:
        print(f"\n📂 Input: {args.input}")
        print(f"📁 Output: {output}")

        encryptor = TokenadeEncryptor()

        with open(input_file, 'rb') as f:
            encrypted = f.read()

        rekeyed = encryptor.rekey(encrypted, old_password, new_password)

        with open(output, 'wb') as f:
            f.write(rekeyed)

        print("\n✅ Rekeyed successfully")
        print(f"   Output: {output}")

    except SystemExit:
        raise
    except ValueError as e:
        print("❌ Wrong old password or corrupted file")
        logger.debug(f"Rekey error: {e}")
        raise SystemExit(1) from e
    except Exception as e:
        logger.error(f"Rekey failed: {e}", exc_info=True)
        print("❌ Rekey failed — verify old password and file integrity")
        raise SystemExit(1) from e
