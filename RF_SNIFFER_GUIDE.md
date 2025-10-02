# RF Sniffer Guide

## What It Does

The RF sniffer listens for ALL RF signals on 433/315MHz and shows you:
- Raw RF codes
- Decoded lamp ID and command (if recognized)
- Timing between signals (gaps)
- Potential echoes or responses from lamps

## How to Use

### Basic Usage

```bash
# Run the sniffer (uses GPIO 23 by default)
python3 rf_sniffer.py

# Use a different GPIO pin
python3 rf_sniffer.py -r 27
```

### Running Alongside Main Program

**Option 1: Two SSH sessions**
```bash
# Terminal 1: Run main program
python3 lamp_control_mqtt.py

# Terminal 2: Run sniffer
python3 rf_sniffer.py
```

**Option 2: Background main program**
```bash
# Run main program in background
python3 lamp_control_mqtt.py &

# Run sniffer in foreground
python3 rf_sniffer.py
```

**Option 3: Use systemd service**
```bash
# Main program runs as service
sudo systemctl start mqtt_lamp_control_rf

# Run sniffer
python3 rf_sniffer.py
```

## What to Look For

### 1. **Do Lamps Echo Commands?**

When you send a command via HomeKit:
- You should see the RF code we transmitted
- **Look for a second signal 50-500ms later with the same code**
- If you see this, the lamp might be echoing back!

Example output if lamp echoes:
```
[0001] 14:23:45.123
  Code: 3513633
  Decoded: Living Room - ON_OFF_OFFSET
  
[0002] 14:23:45.234
  Code: 3513633
  Decoded: Living Room - ON_OFF_OFFSET
  Gap: 111.0ms
  ⚠ Possible echo/response? (gap=111.0ms)
```

### 2. **Command Timing**

Watch the gaps between signals:
- **< 200ms**: Marked as DUPLICATE (filtered by main program)
- **50-500ms**: Flagged as possible echo
- **> 500ms**: Separate commands

### 3. **Physical Remote vs Our Commands**

When you press the physical remote:
- You'll see the RF code
- The sniffer will decode it
- You can compare timing with our transmitted commands

### 4. **Unknown Signals**

If you see "UNKNOWN" signals:
- Could be other RF devices (garage door, weather station, etc.)
- Could be interference
- Note the codes - might be useful for adding new lamps

## Experiments to Try

### Experiment 1: Check for Lamp Echoes
1. Start the sniffer
2. Send an ON/OFF command via HomeKit
3. Watch for duplicate signals within 50-500ms
4. If you see them, the lamp is echoing!

### Experiment 2: Command Loss Detection
1. Start the sniffer
2. Send brightness commands via HomeKit
3. Count how many RF signals you see
4. Compare to expected number (should see multiple for brightness changes)

### Experiment 3: Physical Remote Timing
1. Start the sniffer
2. Press and hold brightness up on physical remote
3. Watch the timing between signals
4. This shows the lamp's natural command rate

### Experiment 4: Interference Check
1. Run sniffer for 5 minutes with no commands
2. See if you receive any signals
3. Unknown signals = RF interference in your environment

## Interpreting Results

### If Lamps DO Echo:
✅ **Great news!** We can detect command success
- We could implement retry logic for failed commands
- We could verify state changes
- This would be a major reliability improvement

### If Lamps DON'T Echo:
❌ **Expected** - Most cheap RF lamps don't echo
- We're stuck with one-way communication
- Current approach (extra commands at boundaries) is best we can do
- Focus on improving RF signal quality instead

## Output Format

```
[0001] 14:23:45.123          ← Signal number and timestamp
  Code: 3513633               ← Raw RF code
  Decoded: Living Room - ON_OFF_OFFSET  ← Lamp and command
  Gap: 234.5ms                ← Time since last signal
  ⚠ Possible echo/response?  ← Warning if timing suggests echo
```

## Tips

- Run for at least 5 minutes to see patterns
- Try different lamps - some might echo, others might not
- Try different distances - echoes might only work close to lamp
- Save output to file: `python3 rf_sniffer.py > rf_log.txt`

## Troubleshooting

**No signals received:**
- Check GPIO pin number (default: 23)
- Verify RF receiver is connected
- Try pressing physical remote - should see signals

**Too many signals:**
- You might have RF interference
- Other devices using same frequency
- Try different location for Pi

**Can't run alongside main program:**
- Both programs use the same GPIO pin
- Use different GPIO pin for sniffer: `python3 rf_sniffer.py -r 27`
- Or stop main program first

