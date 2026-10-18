## Design guide: clean designs and guides a beginner can follow

These rules apply to every model that drives the Physical Studio tools (OpenAI, DeepSeek, Gemini,
Claude, or any MCP client).

### Parts and colors
- Every number comes from get_part. Never take a size from an image, a web page or memory.
- Set `color` on place_part to match the prompt: a traffic light's LEDs are red, yellow and green
  from top to bottom, and an LED next to a button matches it. If the prompt doesn't say, leave it out.
- Name parts the way a beginner would say them: "Red button", "Green LED", "Buzzer", "Arduino Uno".
  Give each copy of a part its own name. Never use an id like `led-5mm-2` as a name.

### Real looks
- If you can't browse the web, call find_part_looks once with every placed part that has no
  `appearance` in get_part; the server looks them up. Otherwise do it yourself:
- Before exporting, look up each part you placed (manufacturer page first, then a shop listing) and
  call set_part_look with what the real part looks like: the PCB's solder-mask color, the metal's
  finish (bare steel about metallic 0.9 / roughness 0.3; a PCB metallic 0 / roughness 0.5) and,
  for boards, top_image_url: the image file of a straight-on top view. Pass the page in `source`.
- Skip a part you can't identify for sure (an unbranded motor); its library look stays. Parts that
  already have a library look (get_part's `appearance`) only need a call if the real one differs.
- Sizes still come from get_part only: a photo never changes a dimension.

### Layout
- Put the main board at the origin first, then everything else around it.
- Parts that poke through the lid (buttons, LEDs) sit in the lid, not floating above the board.
  Line their lid mounts up at the same height (create_enclosure says how far to raise any that are
  low), and keep them clear of the board's tall parts.
- Keep ports a cable plugs into (USB, barrel jack) against a wall so they get a cutout.

### Mechanism builds (motors, rails, gears, arms, frames)
- No case unless the request asks for one. A base plate or frame part is the first placement.
- Build it in the order hands really do it: rail on the base, carriage on the rail, plate on the
  carriage, motor on the plate, gear on the motor shaft, then bearings, shafts and arms, then
  sensors on their mounts, then the boards on the base, then wiring with power last.
- Parts that must line up (a pinion meshing a rack, a magnet centred under an encoder chip, a shaft
  through two bearings) get a callout and a check line about exactly that.
- Leave cable slack for anything that moves, and say so in the wiring step.
- The power supply stays unplugged until the last wire is in; the last wiring step's check says so.

### The check-and-fix loop
- After every placement change: check_interference, check_clearance, then render_preview twice:
  `iso` with the lid hidden (`hide: ["lid"]`) and `top`. Look at both pictures.
- Fix what they show with move_part (a board's screws move with it) or remove_part (for example a
  screw whose head hits a component), then run the checks and previews again.
- Stop only when check_interference is clean, check_clearance has no blocking problems, and the
  previews show nothing floating, overlapping or poking out of the case.

### The assembly guide (add_step)
- Case builds: base, board, screws, then the lid parts, then wiring, then close the lid.
- Every step that adds a part has motion (from_offset, e.g. [0, 0, 40] to drop it in from above), so
  the viewer animates it into place. Every screw, set screw, press-fit or glue step names its tool.
- Lid-mounted parts go in with the lid: turn the lid upside down, press the buttons and LEDs into it,
  then wire them. Don't show them hanging in the base.
- One step per part. Wiring gets its own steps, a few wires each, grouped by part ("Wire the red
  button").
- Each step's text is one or two short sentences in plain words. Name the tool if one is needed.
- Each step's check line is something a camera can see: "The red button sits in the top-left hole of
  the lid", not "The circuit works".
- Call check_guide before export and fix everything under `problems`.
