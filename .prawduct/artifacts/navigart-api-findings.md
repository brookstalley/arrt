# navigart API Findings

Captured 2026-10-06 by probing navigart.fr before writing the `navigart` source
plugin (`arrt/src/arrt/library/sources/navigart.py`). Everything below is
**measured**, with a generic agent string and one request at a time, except
where a line says it is read from the API's own documentation
(`https://api.navigart.fr/`). The durable form is
`arrt/tests/live/test_navigart_shapes_are_still_real.py` (`live_museum`). The
recorded answers the unit suite reads are in `arrt/tests/fixtures/navigart/`.

## What navigart is

- Videomuseum's collection platform. `www.navigart.fr/<slug>/` is one
  *publication* (one collection's catalogue), a JavaScript front end. Its data
  comes from `https://api.navigart.fr/<vault>`, and each publication's front-end
  bundle names that base.
- **The API is documented** ("Navigart 3 API Documentation", `api.navigart.fr/`).
  According to that documentation, a publication is public by default, and then
  "everyone have access to it and could see datas". A publication made private
  needs an account and a token. Only `artworks` is populated. The documentation
  also tells customers to ask Videomuseum for their vault and server. Public
  vaults answered with no key.
- `api.navigart.fr/robots.txt` disallows the documentation pages and the root.
  It does not disallow the vault paths. `www.navigart.fr/robots.txt` disallows
  intranet and app paths only, plus GPTBot entirely.
- No rate limit was found. About 330 API requests over the probe, one at a
  time, met no refusal and no `Retry-After` header. Answers carry
  `Cache-Control: public, max-age: 3600` and come from a server named `thin`.

## The artwork record

- `GET /<vault>/artworks/<id>` answers `{"results": [ {"_id": "<id>", "_source":
  {"ua": {"artwork": {…}, "authors": […], "medias": […]}}} ]}`. `_id` is a
  string.
- Fields read:
  - `ua.artwork.title_notice` (one MAM Paris title holds a line break: `Composition n°27\nJaune assez animé`);
  - `ua.artwork.copyright`;
  - `ua.authors[].type` and `.name.notice`;
  - `ua.medias[]` with `type`, `file_name`, `url_template`, `max_width` and
    `max_height`. The widths and heights are floats such as `777.0`.
- **Authors are written surname first, in capitals**, and an alias or birth name
  sits in brackets: `TAEUBER-ARP Sophie (TAEUBER Sophie-Henriette, dite)`,
  `DELAUNAY Sonia (STERN TERK Sarah Sophie, dite)`, `DORÉ Gustave`, `MATTA
  (MATTA ECHAURREN Roberto …, dit)`. Author types seen in a sample of 235
  records: `artiste` 229, `anonyme` 4 (named `sans auteur`), `groupe` 2,
  `attribution` 1. One record lists `sans auteur` before Doré.
- Artwork types in the same sample: `individual` 224, `separable` 11 (each
  element is an artwork of its own).
- **An artwork the vault does not have is HTTP 404 with `{"error":"Not
  found"}`.** An ID of the wrong form is 400 `{"error":"id is invalid"}`. A vault
  that does not exist (`/7/`) gets nginx's own HTML 404. Vault 999 is 401
  `{"error":"Unauthorized"}`.
- `GET /<vault>/artworks?ids=a,b` and `?size=&from=` page through a vault.
  Totals: Grenoble 9,282, FNAC 92,434, MAM Paris 16,206, Musée Picasso 23,638,
  Nantes 14,146, MAMCS 18,485.

## Which vault a page asks

- **Most artwork IDs begin with their vault's number**: Grenoble `6…`
  (fourteen digits), FNAC `14…`, MAM Paris `18…`, Picasso `16…`, Nantes `11…`,
  MAMCS `25…`, and so on.
- **Not all.** `matisse_lecateau`'s IDs begin with `7`, but its front end asks
  vault `701`, and vault `7` gets nginx's 404. The vault therefore comes from the
  publication, and the plugin keeps a table of them.
- Each publication's vault was read from its own front-end bundle (2026-10-06):

  | Slug | Vault | Slug | Vault | Slug | Vault |
  |---|---|---|---|---|---|
  | bonnard | 51 | fracal | 31 | mamcs | 25 |
  | bourdelle | 19 | fracgrandlarge | 43 | mamparis | 18 |
  | cantini | 53 | fracsud | 45 | matisse_lecateau | 701 |
  | capc | 4 | grenoble | 6 | mdig | 65 |
  | carredart | 50 | lam | 28 | museedartsdenantes | 11 |
  | ceret | 5 | lapiscine | 23 | picassoparis | 16 |
  | fac-pariscollections | 20 | lesabattoirs | 27 | ungerer | 26 |
  | fcac | 58 | MAMC-saint-etienne-collections | 24 | | |
  | fontevraud | 63 | macs | 30 | | |
  | | | macval | 29 | | |

- `fnac` now gets a 301 to `collection.cnap.fr`, and its vault 14 still answers
  FNAC IDs. `grenoble-collections` gets a 301 to `grenoble`, and its IDs are
  vault 6's. `collection-en-ligne` is a 404.

## The image

- `url_template` is `https://images.navigart.fr/{size}/{file_name}`, and
  `file_name` looks like `5E/76/5E76440.JPG`.
- **Sizes served: 100, 200, 300, 400, 600, 800 and 1000.** 50, 150, 250, 255,
  500, 999, 1200, `full` and `max` get 404, and 2000 gets 415.
- **At 1000 the host serves `max_width` × `max_height`**, which is never more
  than 1,000. Checked by reading the served JPEG's header on five images:
  1000 × 979, 777 × 1000, 703 × 942, 366 × 495 and 634 × 405. Under 1,000 the
  host does not upscale, so 800 on a 634 × 405 image gives 634 × 405.
- A missing file gets 415.

## What Wikidata reaches

- **Five ID properties have a navigart formatter:** P6374 MAM Paris (1,777
  items), P12301 MAMCS (841), P11945 Nantes (459), P12213 FNAC (378; preferred
  formatter `…/fnac/artwork/$1`), and P6358 Musée Picasso (300; formatter
  `…/picassoparis/#/artwork/$1`). P6374 has a second formatter on
  `www.mam.paris.fr`, and P12213 one on `www.cnap.fr`. Neither is claimed.
- **"Described at URL" (P973) holds 1,605 navigart links** across about 30
  publications. The largest are `macs` 376, `fnac` 271, `grenoble-collections`
  234, `grenoble` 146 and `MAMC-saint-etienne-collections` 131.
- **The spellings, by count:**

  | Shape | Links |
  |---|---|
  | `/<slug>/#/artwork/<id>` | 700 |
  | `/<slug>/artwork/<id>` | 214 |
  | `/<slug>#/artwork/<id>` | 42 |
  | `/<slug>/artwork/<artist-and-title-words>-<id>` | 9 |
  | `http://` | 4 |
  | `/#/artwork/<id>?note=no` | 2 |

  Some links are an artist's page (`/artworks/authors/<name>`), which is not an
  artwork. Five P12213 values are slugged (`cecile-ferrere-la-vierge-140000000080312`)
  and one is not an ID at all (`ia4572548`).
- 5,258 items link a navigart page. 4,949 of them name an artwork ID, and 1,128
  have an image (P18).
- **Sample:** 256 items, up to 12 per vault prefix, over 24 prefixes, each read
  at the vault its ID prefix gives:
  - 235 answered 200 and 21 got 404. Twelve of those 404s are `matisse_lecateau`
    asked at vault 7, which the table fixes; the other nine are artworks the
    vault no longer has.
  - **228 of the 235 have an image.** 219 are exactly 1,000 px on the long
    side, 9 are smaller (the smallest 407), and none is larger.
  - **175 of the 228 are items with no P18.**
  - Rights: 140 `©…` and 95 `Domaine public`. In a sample of 600 records over
    six vaults, the values were `Domaine public` 201, `© droits réservés` 162,
    `© Adagp, Paris` 121, `© Succession Picasso` 24, other `©` lines, and 4
    empty.

## The corpus

- **Row 6**, Sonia Delaunay, *Rythme couleur n°1076* (Q116464677). Its FNAC ID
  (P12213) is `140000000027457`, giving `https://www.navigart.fr/fnac/artwork/140000000027457`.
  Image 1000 × 979, `© Pracusa S.A.`
- **Row 14**, Taeuber-Arp, *Échelonnement* (Q136030970). P973 is
  `https://www.navigart.fr/grenoble/#/artwork/60000000002521`. Image 777 × 1000,
  `Domaine public`. navigart titles it `Echelonnement`, without the accent.
- **Row 7**, Delaunay, *Rythme* (Q104423957). It links only Paris Musées'
  pages, so navigart does not reach it. The Musée d'Art Moderne de Paris is in
  both navigart (vault 18) and Paris Musées (#233). A work found by both would
  be offered under two providers, which the pool ranks as any two sources.
- Every image here is under the floor on the owner's panel (about 1,060 px), so
  each is offered as a placeholder.
