/* A wall or a client named on a page that is not its own: a link to it.
 *
 * `information-architecture.md` § Direction: navigation is a link. A wall is
 * addressed as Walls with that wall's card in view (`#walls?wall=<id>`), a
 * client as Clients with its panel in view (`#clients?client=<id>`), because
 * neither has a page of its own: each lives on its sidebar page among the
 * others, and the address says which one the reader came for. The page marks
 * that one `data-arrive`, and the router puts the keyboard and the scroll there
 * (`core/router.js`, `refresh`). */

import { link } from "./router.js";

export function wallLink(wallId, name) {
  return link({ view: "walls", params: { wall: wallId } }, { class: "link", text: name });
}

export function clientLink(clientId, name) {
  return link({ view: "clients", params: { client: clientId } }, { class: "link", text: name });
}

/* Each of `walls` as its link, between commas: the walls a work or a theme
 * hangs on. */
export function wallLinks(walls) {
  return walls.flatMap((wall, at) => (at ? [", ", wallLink(wall.wall_id, wall.name)] : [wallLink(wall.wall_id, wall.name)]));
}
