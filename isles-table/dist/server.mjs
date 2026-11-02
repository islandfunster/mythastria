// PLAYER-SITE-01 (GM 2026-10-28: the player client is a hosted HTML site): where the GM's Mythastria answers. On the GM's
// own PC and through the players' door the pages and the service share one address, so SERVER is ''. On the hosted
// site (player-client/build_player_client.py --site) each page carries <meta name="mythastria-server" content="https://...">
// and every call, and every picture the GM's PC holds (maps, tokens, chat pictures), goes there instead.
const meta = globalThis.document?.querySelector?.('meta[name="mythastria-server"]');
export const SERVER = (meta?.content || '').replace(/\/+$/, '');

// A service route ('/api/...') at the GM's Mythastria.
export const api = path => SERVER + path;

// A picture or sound named by the game's data: a path on the GM's PC ('maps/x.png', '/chat-media/y.webp'); data:,
// blob: and full addresses stay as they are.
export function asset(path) {
  if (!SERVER || typeof path !== 'string' || !path || /^(?:[a-z][a-z0-9+.-]*:|\/\/)/i.test(path)) return path;
  return SERVER + (path.startsWith('/') ? '' : '/') + path.replace(/^\.\//, '');
}

// A picture from the GM's PC that is drawn on a canvas or in the 3D view: asked for with CORS on the hosted site, so the
// browser lets the page use its pixels (the players' door allows the hosted site's address).
export function load(image, path) {
  if (SERVER) image.crossOrigin = 'anonymous';
  image.src = asset(path);
  return image;
}
