// What each build decodes the panel's source data to. Written by
// tools/write_expected.js; see there for when to run it again.
//
// Keyed by the fingerprint of the modules that produced the hashes, the same
// one decoder-version.json carries. A page can be running decoders from an
// older deployment than the one it fetched this from, so the builds accumulate
// here and each is held to its own numbers.
export const EXPECTED = {
  "e5f57f2aa0090a1a": {
    restoration: "471e19dc815c0c3706b67dd4b4b09856314bff76aa6a25502bf4d7abac70a57f",
    worldMap: "4bb90b6024331fed54a0ad80a961b3e461bfff1370b3ff6d30015a27078443dd",
  },
  "3489d6b137c71db7": {
    restoration: "77a929dcc2dc28ae383fe6e5973498f6d6cece2b721660eac83d9963ac3cc630",
    worldMap: "4bb90b6024331fed54a0ad80a961b3e461bfff1370b3ff6d30015a27078443dd",
  },
  "32016049560715c3": {
    restoration: "91d8f9c39bebb5b62e41e7ca9ad437a0df0bbbc37459b1e5d07cd04548f6b26b",
    worldMap: "4bb90b6024331fed54a0ad80a961b3e461bfff1370b3ff6d30015a27078443dd",
  },
  "28a9f060298263c2": {
    restoration: "d78dddaa76c1c85cce1a8669a54beee18f63fbc4db2712f62d59050102773cec",
    worldMap: "4bb90b6024331fed54a0ad80a961b3e461bfff1370b3ff6d30015a27078443dd",
  },
  "8e2d9b5921c56069": {
    restoration: "c6856fb6cd2a4588aa6fa12d5fe99a79601dc556d9420d4cb758dd2358bd4b9f",
    worldMap: "4bb90b6024331fed54a0ad80a961b3e461bfff1370b3ff6d30015a27078443dd",
  },
  "1e885e7b67ff1a65": {
    restoration: "c6856fb6cd2a4588aa6fa12d5fe99a79601dc556d9420d4cb758dd2358bd4b9f",
    worldMap: "4bb90b6024331fed54a0ad80a961b3e461bfff1370b3ff6d30015a27078443dd",
  },
  "0dd9c644402b0a40": {
    restoration: "c6856fb6cd2a4588aa6fa12d5fe99a79601dc556d9420d4cb758dd2358bd4b9f",
    worldMap: "4bb90b6024331fed54a0ad80a961b3e461bfff1370b3ff6d30015a27078443dd",
  },
  "c8a1b9bce7f811ae": {
    restoration: "79b541cb7f8fa7bf50a2f6b571b4d996431c65e5b794a44beaae5071ba8e99c2",
    worldMap: "4bb90b6024331fed54a0ad80a961b3e461bfff1370b3ff6d30015a27078443dd",
  },
};
