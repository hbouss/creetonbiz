// frontend/crypto-polyfilltest.cjs
const { webcrypto } = require('node:crypto');
const { Buffer } = require('buffer');

// On récupère l'objet crypto existant (Web Crypto ou Node webcrypto)
const cryptoObj = globalThis.crypto || webcrypto;

// Si la méthode hash n'existe pas, on la définit
if (!cryptoObj.hash) {
  Object.defineProperty(cryptoObj, 'hash', {
    value: async (algorithm, data, outputEncoding) => {
      // Normalise les données en Buffer
      const buf =
        typeof data === 'string'
          ? Buffer.from(data)
          : Buffer.from(data instanceof ArrayBuffer ? new Uint8Array(data) : data);
      // Utilise subtle.digest pour le hash
      const arrayBuffer = await (webcrypto.subtle || webcrypto).digest(algorithm, buf);
      if (outputEncoding) {
        return Buffer.from(arrayBuffer).toString(outputEncoding);
      }
      return arrayBuffer;
    },
    writable: true,
    configurable: true,
  });
}