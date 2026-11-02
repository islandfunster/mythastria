# Mythastria

A virtual tabletop where everyone plays in their own playstyle, together. Talking, exploring and fighting all share one table and one story.

Mythastria runs SRD 5.2.1 games. The rules engine runs on the GM's own PC, the table opens in a browser, and players can join from their own screens.

The rules and creature turns are plain Python. No AI model is needed to play.

## What you need

- Windows 10 or 11. Other systems haven't been tested.
- [Python 3.12 or newer](https://www.python.org/downloads/). In the installer, tick **Add python.exe to PATH** and keep **py launcher** ticked.

There's nothing else to install.

## Start it

1. Download this repository into a short folder, for example `C:\Games\mythastria`.
2. Double-click `engine\Start_Mythastria.bat`.
3. Mythastria opens in your browser at <http://127.0.0.1:8772/>. Keep the window open while you play.

## Your first game

1. Build or import a character on **Characters**, then save it.
2. On **Play live**, tick it under **Saved characters**.
3. Press **Start live fight**.

## Adventures

Mythastria comes with no adventure. [Seven Isles](https://github.com/islandfunster/mythastria-adventure-packs) is a free one, and its page shows how to load it.

## Playing with others

- On one PC, everyone can play from the same screen.
- Players on their own devices join through the players' door at <http://127.0.0.1:8782/>. You let each one in on Play live, under **Players...**.
- Reaching your PC from the internet needs a tunnel of your own: see [Playing over the internet](#playing-over-the-internet).

If you open a table to other people, you run it and you're responsible for it. Players accept the notice in `isles-table\dist\table-notice.json` before they join. Read it, change it to fit your table, and get your own legal advice. Change its `version` whenever you change its text, so players are asked again.

## Playing over the internet

Mythastria runs on your PC, so players' screens need a way to reach it. Discord or another voice app carries the talking and the invite link, but it doesn't connect anyone to the game. For that you need a tunnel with a public web address. You set this up once, and players install nothing.

These steps use a Cloudflare Tunnel. It leaves your router closed and keeps your home address hidden. You need a free Cloudflare account and a domain name of your own. Cloudflare's screens change over time, so follow [its tunnel guide](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/) if they look different.

### Set it up once

1. Add your domain to your Cloudflare account.
2. In Cloudflare's Zero Trust dashboard, create a tunnel and install its connector on your PC with the command it gives you.
3. Give the tunnel a public hostname, such as `play.example.com`, with the service `http://127.0.0.1:8782`. Use only this port: the players' door is 8782, and 8772 is your GM screen.
4. Create `engine\local_settings.cmd` with that hostname, spelled exactly the same:

   ```
   set "PLAYERS_HOST=play.example.com"
   ```

Keep your Cloudflare sign-in and the tunnel's key private, and never put them in this repository.

### On game night

1. Make sure the tunnel is running, then double-click `engine\Start_Mythastria.bat`.
2. On **Play live**, open **Players...** and copy the invite link.
3. Paste the link into your Discord server or other chat.
4. Players open it in a browser, accept the notice and ask to join.
5. Let each player in under **Players...**.

Keep your PC on and the Mythastria window open while you play.

### If it doesn't work

| What you see | Do this |
|---|---|
| Unknown host for the players' door | `PLAYERS_HOST` doesn't match the tunnel's name. Correct it, then start Mythastria again. |
| The page doesn't load for players | Check that the tunnel and the Mythastria window are both running, and that the tunnel points at port 8782. |

### Other tunnels

Another tunnel service can work if it sends the public name through to port 8782, but this hasn't been tested. The door can only tell visitors apart behind Cloudflare, so elsewhere one player's wrong invite codes may block everyone for five minutes.

## Adventures

Adventure modules go in an `adventures` folder beside `engine`, as `adventures\<module>\adventure.json`. Load one on **Play an adventure**. Mythastria comes with no adventure; without one, Play live has the included test maps.

## AI models (optional)

Chat can load a local model through LM Studio or Ollama, and the Rules monitor uses it to read play beside the engine. A model never decides a rule.

## Your own settings

Create `engine\local_settings.cmd` to change folders or ports. It stays on your PC:

```
set "PACKS=D:\My Adventures"
set "PORT=8772"
set "PLAYERS_PORT=8782"
```

Map notes, imported maps, saved Remix choices, chat pictures and sounds, logs and local settings stay in your folder. Git ignores them. Characters you make are saved in your browser.

## Tests

Run a test file from the `engine` folder, one at a time:

```
py -3 -m unittest test_map_rule
```

Some tests fail on small mismatches in old test data. Two known ones are `test_vocational_creatures` and one test in `test_srd_library`.

## Give back

Those of us who play games have leisure time. Let's not forget that there are needy people in the world. Please donate to local volunteer efforts, whether it's your time or your money.

## Licence and credits

Mythastria's code and art are under the MIT License: see [LICENSE](LICENSE) and [CREDITS](isles-table/CREDITS.md).

This work includes material from the System Reference Document 5.2.1 ("SRD 5.2.1") by Wizards of the Coast LLC, available at https://www.dndbeyond.com/srd. The SRD 5.2.1 is licensed under the Creative Commons Attribution 4.0 International License, available at https://creativecommons.org/licenses/by/4.0/legalcode.

Mythastria adapts this material and changes some of its rules with its own rulings, and leaves others to the GM. The **By the SRD** switch on Play live plays Hide and Spirit Guardians as the SRD writes them. Mythastria is not affiliated with or endorsed by Wizards of the Coast.
