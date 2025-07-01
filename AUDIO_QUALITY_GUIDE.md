# 🎵 Audio Quality & Speed Buffer Guide

## Overview
PuddlesBot now includes advanced audio quality management and speed buffering to ensure consistent, high-quality music playback. These optimizations work at both the Lavalink server level and the bot application level.

## 🚀 **What's Been Improved**

### **1. Lavalink Server Optimizations**
- **Increased Buffer Size**: From 400ms to 800ms for smoother playback
- **Extended Frame Buffer**: From 5000ms to 8000ms for better audio continuity
- **High-Quality Resampling**: Upgraded from LOW to HIGH quality
- **Optimized YouTube Clients**: Prioritized high-quality audio sources
- **Faster Player Updates**: Reduced from 5s to 2s for real-time sync
- **Memory Optimization**: Enabled non-allocating frame buffer

### **2. Speed Buffer & Consistency**
- **8-second audio buffer** prevents stuttering and dropouts
- **Smooth seek transitions** with ghosting enabled
- **Auto-reconnection** on connection issues
- **Preload next track** for seamless playback
- **Connection pooling** for stable streaming

### **3. Quality Presets**
Four quality presets to match your server's capabilities:

| Preset | Buffer | Quality | CPU Usage | Best For |
|--------|--------|---------|-----------|----------|
| **Ultra High** | 12s | 10/10 | High | High-end servers |
| **High** | 8s | 10/10 | Medium | Recommended for most |
| **Balanced** | 5s | 8/10 | Medium | Busy servers |
| **Performance** | 3s | 6/10 | Low | Resource-limited |

## 🎛️ **Commands**

### **View Current Quality**
```
/quality status
```
Shows current quality preset and technical details.

### **Change Quality Preset**
```
/quality preset
```
Shows all available presets with descriptions.

```
/quality preset high
```
Applies the "high" quality preset (requires Manage Server permission).

### **Get Quality Information**
```
/quality info
```
Explains how different settings affect audio quality.

### **View Audio Statistics**
```
/audiostats
```
Shows real-time player status and performance metrics.

## ⚙️ **Technical Details**

### **Buffer Size Explained**
- **Higher values** = Smoother playback but slightly more delay
- **Lower values** = Less delay but potential for stuttering
- **Recommended**: 8000ms (8 seconds) for most servers

### **Resampling Quality**
- **HIGH**: Best audio quality, uses more CPU
- **MEDIUM**: Balanced quality and performance  
- **LOW**: Performance mode, lower quality

### **Opus Encoding Quality**
- Scale from 0-10 where 10 is highest quality
- Set to 10 for maximum audio fidelity
- Higher values use more CPU but sound significantly better

## 🔧 **Advanced Configuration**

### **For Server Administrators**
The quality presets can be changed using `/quality preset <name>` with these permissions:
- `Manage Server` permission required
- Changes apply to new songs immediately
- Current song needs to be restarted to apply new settings

### **Performance Monitoring**
Use `/audiostats` to monitor:
- Player connection status
- Current track information
- Buffer and quality settings
- Real-time performance metrics

## 📊 **Quality Recommendations**

### **For Most Servers (Recommended)**
```
/quality preset high
```
- 8-second buffer for smooth playback
- Maximum Opus quality (10/10)
- High resampling quality
- Balanced CPU usage

### **For High-Traffic Servers**
```
/quality preset balanced
```
- 5-second buffer (still very smooth)
- Good quality (8/10)
- Lower CPU usage
- Reliable for busy environments

### **For Premium Experience**
```
/quality preset ultra_high
```
- 12-second buffer (ultra smooth)
- Maximum quality settings
- Prefers lossless sources when available
- Requires powerful server

### **For Resource-Limited Servers**
```
/quality preset performance
```
- 3-second buffer (minimal delay)
- Performance-optimized quality
- Low CPU usage
- Good for shared hosting

## 🎵 **Audio Sources Priority**

The system now prioritizes audio sources for best quality:

1. **YouTube Music** - Highest quality music-focused streams
2. **Android Music** - High-quality mobile streams  
3. **Android VR** - Optimized audio streams
4. **TV HTML5** - High-quality TV client streams
5. **Web** - Standard web quality
6. **Web Embedded** - Fallback option

## 🔄 **Real-Time Adjustments**

### **Automatic Features**
- **Auto Quality**: Automatically selects best available quality
- **Smart Buffering**: Adjusts buffer based on connection stability
- **Seamless Transitions**: Smooth track changes with preloading
- **Connection Recovery**: Auto-reconnects on network issues

### **Manual Controls**
- Change quality presets anytime with `/quality preset`
- Monitor performance with `/audiostats`
- Get help with `/quality info`

## 🚨 **Troubleshooting**

### **If Audio Keeps Cutting Out**
1. Use `/quality preset high` for better buffering
2. Check `/audiostats` for connection issues
3. Consider upgrading to `ultra_high` preset

### **If There's Too Much Delay**
1. Use `/quality preset balanced` for less buffering
2. Try `performance` preset for minimal delay
3. Check your server's CPU usage

### **If Quality Sounds Poor**
1. Ensure you're using `high` or `ultra_high` preset
2. Check if the audio source supports high quality
3. Use `/audiostats` to verify current settings

## 📝 **Notes**

- Quality changes apply to new songs immediately
- Current songs need to be restarted (`/skip` then `/play` again) for immediate effect
- Higher quality settings use more server CPU and bandwidth
- The `high` preset is recommended for most users as it provides excellent quality with reasonable resource usage

## 🎉 **Enjoy Your Enhanced Audio Experience!**

With these optimizations, your music should now sound clearer, play more consistently, and have fewer interruptions. The smart buffering system ensures smooth playback even on less stable connections. 