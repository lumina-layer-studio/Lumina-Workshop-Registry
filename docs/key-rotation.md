# Registry Ed25519 key rotation

## Trust boundary

The signing private key is generated outside Git and stored only in the
review-gated `registry-production` GitHub Environment. The repository contains
only a raw 32-byte Ed25519 public-key record. Lumina embeds its own trusted key
set; the Registry cannot make an application trust a new key.

## Planned rotation

1. Generate a new Ed25519 pair to explicit local paths on a trusted machine.
2. Record the public key in a reviewed Lumina release and retain the old key
   during an overlap window.
3. Ship and verify Lumina with both trusted public keys.
4. Add the new public record to this repository and update the Environment
   secret through the GitHub secret UI or API without printing its value.
5. Publish and independently verify an index signed by the new key.
6. After the supported-client overlap window, remove the retired public key
   in a later Lumina release.

Never replace a key under an existing key ID. Never attach a private PEM to a
PR, artifact, cache, log, shell trace, Pages payload, support ticket, or module
package.

## Emergency compromise response

Pause the `registry-production` Environment, block affected module versions as
needed, rotate to a previously app-trusted recovery key, and publish a Lumina
security update. Because clients trust app-owned keys and preserve the last
verified cache, invalid remote data cannot silently replace a verified local
Registry.

