/** The only loopback routes the renderer may reach through the preload bridge. */
const allowed = /^\/(health|catalog\/(home|search(?:\/suggestions)?|rank|browse|filters|comments|danmaku|series\/\d+(?:\/(next-season|seasons))?)|reservations\/upcoming|account\/(session|send-code|login|logout|history|favorites|progress|favorite|reservations?|mfa\/(send|verify)|qr(?:\/[a-f0-9]{32})?)|media\/(session(?:\/[a-zA-Z0-9_-]+)?|cache(?:\/(clear|settings))?|cached|prefetch|probe))(\?[^\r\n#]*)?$/;

export const MAX_ROUTE_LENGTH = 3000;

/** Rejects anything the service does not serve; the query string may only be plain. */
export function allowedRoute(route: unknown): route is string {
  return typeof route === 'string' && route.length <= MAX_ROUTE_LENGTH && !/[\r\n#]/.test(route) && allowed.test(route);
}
