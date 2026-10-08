/* The museum or archive behind an image source, by the name a curator knows it by.
 *
 * Image sources are plugins, and each records what it found under its plugin
 * id (`artic`, `nga`, `smk`). That id is a key, not a name: a scan "from artic"
 * says nothing to somebody who knows the Art Institute of Chicago. So every
 * screen that names where a picture came from says it through `museumName`.
 *
 * Keyed by the `PROVIDER` each built-in plugin declares under
 * `library/sources/`, and held to them by `tests/unit/test_client_vocabulary.py`,
 * so a new built-in source fails there until it has a name. A plugin installed
 * from elsewhere is not known here and is named by its id, which is still what
 * it called itself. Imports nothing, so `node` can run it. */

export const MUSEUM_NAMES = {
  artic: "Art Institute of Chicago",
  commons: "Wikimedia Commons",
  getty: "J. Paul Getty Museum",
  met: "Metropolitan Museum of Art",
  navigart: "Navigart (French public collections)",
  nga: "National Gallery of Art, Washington",
  rijksmuseum: "Rijksmuseum",
  smk: "SMK, National Gallery of Denmark",
  wikidata: "Wikidata",
  yale: "Yale art museums",
};

export function museumName(provider) {
  return MUSEUM_NAMES[provider] || provider || "an unnamed source";
}

/* A source plugin's state as a word, by the server's `PluginState`, for Sources
 * and Status alike. Held to the enum by the vocabulary test; one it has no word
 * for is shown as itself. */
export const PLUGIN_STATE_WORDS = {
  loaded: "Loaded",
  declined: "Not configured here",
  failed: "Could not be loaded",
};

/* What is known of a source's rights, as words, by `RightsStatus`. Held to the
 * enum by the vocabulary test; one it has no word for is shown as itself. */
export const RIGHTS_WORDS = {
  public_domain: "Public domain",
  in_copyright: "In copyright",
  unknown: "Not known",
};

/* How the last fetch from a source went, as words, by `FetchStatus`. */
export const FETCH_WORDS = {
  ok: "Fetched",
  partial_tiles: "Fetched, a few tiles missing",
  failed: "Failed",
};
