/**
 * Tokenade WebCrypto Encryption Module
 *
 * Implements AES-256-GCM authenticated encryption/decryption with PBKDF2-SHA256 (600,000 iterations),
 * providing 100% binary format parity with the Python TokenadeEncryptor.
 */

const MAGIC_BYTES = new Uint8Array([
  0x54, 0x4f, 0x4b, 0x45, 0x4e, 0x41, 0x44, 0x45, 0x5f, 0x45, 0x4e, 0x43,
  0x52, 0x59, 0x50, 0x54, 0x45, 0x44,
]); // "TOKENADE_ENCRYPTED"
const VERSION_2 = 2;
const SALT_SIZE = 16;
const NONCE_SIZE = 12;
const KEY_SIZE = 32; // 256-bit
const PBKDF2_ITERATIONS = 600000;

class TokenadeWebCrypto {
  /**
   * Derive an AES-256-GCM CryptoKey from a password and salt using PBKDF2-HMAC-SHA256.
   * @param {string} password
   * @param {Uint8Array} salt
   * @param {number} iterations
   * @returns {Promise<CryptoKey>}
   */
  static async deriveKey(password, salt, iterations = PBKDF2_ITERATIONS) {
    const enc = new TextEncoder();
    const baseKey = await crypto.subtle.importKey(
      "raw",
      enc.encode(password),
      { name: "PBKDF2" },
      false,
      ["deriveKey"]
    );

    return crypto.subtle.deriveKey(
      {
        name: "PBKDF2",
        salt: salt,
        iterations: iterations,
        hash: "SHA-256",
      },
      baseKey,
      { name: "AES-GCM", length: 256 },
      false,
      ["encrypt", "decrypt"]
    );
  }

  /**
   * Encrypt plaintext string or Uint8Array with a password to Tokenade v2 binary format.
   * @param {string|Uint8Array} data
   * @param {string} password
   * @returns {Promise<Uint8Array>}
   */
  static async encrypt(data, password) {
    if (!password) throw new Error("Password is required for encryption");

    const plaintextBytes =
      typeof data === "string" ? new TextEncoder().encode(data) : data;

    const salt = crypto.getRandomValues(new Uint8Array(SALT_SIZE));
    const nonce = crypto.getRandomValues(new Uint8Array(NONCE_SIZE));
    const key = await this.deriveKey(password, salt, PBKDF2_ITERATIONS);

    const ciphertextBuffer = await crypto.subtle.encrypt(
      { name: "AES-GCM", iv: nonce },
      key,
      plaintextBytes
    );
    const ciphertext = new Uint8Array(ciphertextBuffer);

    // Build binary output: MAGIC (18B) + VERSION (4B big-endian) + SALT (16B) + NONCE (12B) + CIPHERTEXT (incl 16B tag)
    const totalLength =
      MAGIC_BYTES.length + 4 + SALT_SIZE + NONCE_SIZE + ciphertext.length;
    const output = new Uint8Array(totalLength);
    let offset = 0;

    output.set(MAGIC_BYTES, offset);
    offset += MAGIC_BYTES.length;

    const view = new DataView(output.buffer, output.byteOffset, output.byteLength);
    view.setUint32(offset, VERSION_2, false); // big-endian
    offset += 4;

    output.set(salt, offset);
    offset += salt.length;

    output.set(nonce, offset);
    offset += nonce.length;

    output.set(ciphertext, offset);

    return output;
  }

  /**
   * Check whether bytes start with the Tokenade encrypted header.
   * @param {Uint8Array} bytes
   * @returns {boolean}
   */
  static isEncrypted(bytes) {
    if (!bytes || bytes.length < MAGIC_BYTES.length + 4) return false;
    for (let i = 0; i < MAGIC_BYTES.length; i++) {
      if (bytes[i] !== MAGIC_BYTES[i]) return false;
    }
    return true;
  }

  /**
   * Decrypt Tokenade binary encrypted bytes using a password.
   * @param {Uint8Array} encryptedBytes
   * @param {string} password
   * @returns {Promise<string>} Decrypted UTF-8 string
   */
  static async decrypt(encryptedBytes, password) {
    if (!this.isEncrypted(encryptedBytes)) {
      throw new Error("Invalid Tokenade encrypted file format (header magic mismatch)");
    }
    if (!password) {
      throw new Error("Password required to decrypt session");
    }

    let offset = MAGIC_BYTES.length;
    const view = new DataView(
      encryptedBytes.buffer,
      encryptedBytes.byteOffset,
      encryptedBytes.byteLength
    );
    const version = view.getUint32(offset, false);
    offset += 4;

    const salt = encryptedBytes.slice(offset, offset + SALT_SIZE);
    offset += SALT_SIZE;

    const nonce = encryptedBytes.slice(offset, offset + NONCE_SIZE);
    offset += NONCE_SIZE;

    let ciphertext;
    if (version === 1) {
      // v1 format had 32-byte HMAC appended at the end
      ciphertext = encryptedBytes.slice(offset, encryptedBytes.length - 32);
    } else {
      // v2 format: raw AES-GCM ciphertext + 16B tag
      ciphertext = encryptedBytes.slice(offset);
    }

    const key = await this.deriveKey(password, salt, PBKDF2_ITERATIONS);

    try {
      const decryptedBuffer = await crypto.subtle.decrypt(
        { name: "AES-GCM", iv: nonce },
        key,
        ciphertext
      );
      return new TextDecoder("utf-8").decode(decryptedBuffer);
    } catch (err) {
      throw new Error("Decryption failed: incorrect password or corrupted data");
    }
  }
}

// Export for extension and browser environments
if (typeof window !== "undefined") {
  window.TokenadeWebCrypto = TokenadeWebCrypto;
}
if (typeof module !== "undefined" && module.exports) {
  module.exports = { TokenadeWebCrypto };
}
