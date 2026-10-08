# Apple platforms: what a macOS screensaver and a tvOS app can do as Players

**What this is.** The evidence behind `feeds-and-players.md` § Platforms, from a
throwaway spike on 2026-10-08. Each fact is labelled **MEASURED** (run on the
owner's Mac), **SOURCED** (a cited document) or **UNVERIFIED**. Nothing was
installed into the system, no setting was changed, and no television or other
network device was contacted. The spike's code lived in a session scratch
directory and was not kept; what it showed is recorded here.

**Host:** the owner's Mac, macOS 27.0, Xcode 27.0, Swift 6.4. The installed SDKs
include tvOS 27.0 and the tvOS simulator (MEASURED, `xcodebuild -showsdks`).

## macOS screensaver

- **A Swift screensaver builds and draws (MEASURED).** A `ScreenSaverView`
  subclass built with plain `swiftc` into an ad-hoc-signed `.saver` bundle. A
  harness loaded the bundle without installing it and rendered one frame
  offscreen: a 300×600 image came out fitted and centred on black. It was **not**
  run inside the real screensaver host.
- **Third-party savers run inside Apple's `legacyScreenSaver.appex` (MEASURED,
  from the host's entitlements).** It is sandboxed, can make and accept network
  connections, can read files anywhere, and can write only to its own
  container's Caches folder. So a saver Player downloads into its own cache, or a
  separate Postarr process writes a cache the saver only reads.
- **The host's defects are concrete (SOURCED: Wade Tregaskis, mjtsai.com,
  Aerial's ScreenSaverMinimal, Apple Developer Forums thread 802525):**
  - Since Sonoma, `stopAnimation` is called only for the Settings preview.
  - Each start creates a new view instance, and old ones keep running.
  - The host process is never killed. The usual remedy is `exit(0)` on the
    `com.apple.screensaver.willstop` distributed notification.
  - Swift savers are supported from macOS 14.6; SwiftUI content crashes in the
    host.
  - Multi-monitor handling is unreliable, and signing and notarising are manual.
- **There is no supported alternative screensaver API (MEASURED).** Apple's newer
  wallpaper and screensaver system is in private frameworks in the SDK. The only
  other route is a full-screen or idle-detecting app, which is not a screensaver.
- **Local network: macOS requires permission (SOURCED, Apple TN3179, since
  macOS 15). Whether a saver plug-in can be granted it is UNVERIFIED** and is
  the largest risk for a macOS Player: neither host carries a local-network
  usage description. If it cannot, a companion app that fills a cache the saver
  only reads is the fallback. Test on a real Mac before the macOS Player's plan
  is written.

## tvOS app

- **Third-party apps cannot be screensavers (MEASURED and SOURCED).** The tvOS
  SDK has no ScreenSaver framework, and Apple's forum thread 17248 says it is not
  offered. The Player is a foreground app.
- **A backgrounded app goes silent (SOURCED, Apple's background execution
  modes).** It gets `willResignActive` and `didEnterBackground` (both compiled,
  MEASURED) and is then suspended. So it cannot keep reporting `in_use`. At most
  it sends one last heartbeat as it leaves, and the server sees a silent wall
  after that. `isIdleTimerDisabled` keeps the Apple TV's own screensaver off
  while art shows.
- **tvOS has no local-network permission (SOURCED, TN3179's platform table).**
  The usage description and Bonjour keys are harmless and unused.
- **The connections a Frame needs compile (MEASURED, compile only, tvOS 18
  device and simulator, no warnings):** a `URLSession` WebSocket to port 8002, a
  Network framework TLS socket accepting any certificate, plain TCP, a Network
  framework WebSocket, and a Bonjour browser. None was run against a set.
- **The Frame's self-signed certificate is the real obstacle (SOURCED: Apple's
  manual server trust and `NSAllowsLocalNetworking` documentation).**
  `URLSession` cannot relax trust for a host App Transport Security covers, its
  local-networking exception is not listed for tvOS, and bare IP addresses need
  explicit exceptions on recent OS versions. Network framework is not subject to
  ATS, so it is the route to a Frame. Whether `URLSession` would work anyway is
  UNVERIFIED without hardware.

## Screen size and density

- **macOS (MEASURED):** `CGDisplayScreenSize` gave 301×196 mm at 3024×1964 px on
  the built-in panel, 255 ppi against a specified 254. The nominal 144 dpi the
  system reports is useless for this. An external TV's reported size is
  UNVERIFIED (none was attached).
- **tvOS (MEASURED, from the SDK headers):** `UIScreen` gives pixels and scale
  only, with no physical size or density.
- **So the mat's relative-width fallback is required, not a contingency**
  (`feeds-and-players.md` § Mat modes): only a Mac's built-in panel reliably
  knows its density.

## Typesetting

**CoreText can do what the label's layout needs (MEASURED on macOS; the same
calls compiled for tvOS):** font metrics, suggested line breaks at a width,
per-line widths and heights, and a block's size, comparable to what
`postarr/src/postarr/panel/legibility.py` takes from Pango. Fonts, shaping and
hyphenation will differ, so the shared conformance vectors check rules (the type
floor, the line limit, whether it fits), never exact pixels.

## Sources

- [TN3179: Understanding local network privacy](https://developer.apple.com/documentation/technotes/tn3179-understanding-local-network-privacy)
- [Performing manual server trust authentication](https://developer.apple.com/documentation/foundation/performing-manual-server-trust-authentication)
- [NSAllowsLocalNetworking](https://developer.apple.com/documentation/bundleresources/information-property-list/nsapptransportsecurity/nsallowslocalnetworking)
- [Configuring background execution modes](https://developer.apple.com/documentation/xcode/configuring-background-execution-modes)
- [Wade Tregaskis: how to make a macOS screen saver](https://wadetregaskis.com/how-to-make-a-macos-screen-saver/)
- [Michael Tsai: How to make a macOS screen saver](https://mjtsai.com/blog/2025/12/10/how-to-make-a-macos-screen-saver)
- [AerialScreensaver/ScreenSaverMinimal](https://github.com/AerialScreensaver/ScreenSaverMinimal)
- [Apple Developer Forums 802525](https://developer.apple.com/forums/thread/802525) and [17248](https://developer.apple.com/forums/thread/17248)
