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
};
