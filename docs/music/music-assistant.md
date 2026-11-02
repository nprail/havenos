# Music Assistant library

With a Music Assistant server configured, the dashboard music card gets a **Library** button (key `l` on a desktop). It lets you browse recents, playlists and albums, search, and tap to play on the display.

> **Status.** The library has been tested against a fake Music Assistant server only. The Sendspin side that plays the result has been verified on a real setup. The URL, token, `play_media` arguments and player lookup are not yet confirmed against a real server.

## Set it up

1. Enable [Sendspin](sendspin.md). Playing from the library asks Music Assistant to start the display's own Sendspin player, so Sendspin must be on.
2. In Music Assistant, open Settings, Profile and create a long-lived token.
3. In the [settings page](../settings-ui.md), Music card, enter the Music Assistant URL and the token and press **Test connection**.

Or in the config file:

```toml
[music.assistant]
url = "http://homeassistant.local:8095"
token_file = "~/.config/havenos/ma_token"
player_id = ""     # empty = find this display's player by its Sendspin name
```

## Using it

Open the Library from the dashboard music card. Browse or search, then tap an item. Music Assistant starts the display's Sendspin player and the arbiter treats it like any other source: if something else was playing, the library takes over.

## Limits

- Search is by physical keyboard or by voice (the mic button in the search bar, when the voice assistant is on). There is no on-screen keyboard, by decision. Voice search uses a Home Assistant speech-to-text provider (Whisper, or Home Assistant Cloud) and is untested on a real one.
- If the player cannot be found by name, set `player_id` explicitly.
