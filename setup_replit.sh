#!/bin/bash
# Setup script for Replit - installs Java 17 and Lavalink manually

echo "🚀 Setting up Lavalink Music System on Replit..."

# Step 1: Install Java 17
echo "📦 Installing Java 17..."
if [ ! -d "java17" ]; then
    wget -q https://download.oracle.com/java/17/latest/jdk-17_linux-x64_bin.tar.gz
    tar -xzf jdk-17_linux-x64_bin.tar.gz
    mv jdk-17.* java17
    rm jdk-17_linux-x64_bin.tar.gz
    echo "✅ Java 17 installed"
else
    echo "✅ Java 17 already installed"
fi

# Set Java environment
export JAVA_HOME=$PWD/java17
export PATH=$PWD/java17/bin:$PATH

# Verify Java installation
echo "🔍 Java version:"
java -version

# Step 2: Download Lavalink
echo "📦 Downloading Lavalink..."
if [ ! -f "Lavalink.jar" ]; then
    wget -q https://github.com/lavalink-devs/Lavalink/releases/latest/download/Lavalink.jar
    echo "✅ Lavalink downloaded"
else
    echo "✅ Lavalink already exists"
fi

# Step 3: Create Lavalink configuration
echo "⚙️ Creating Lavalink configuration..."
cat > application.yml << 'EOF'
server:
  port: 2333
  address: 0.0.0.0
  http2:
    enabled: false

lavalink:
  server:
    password: "youshallnotpass"
    sources:
      youtube: true
      soundcloud: true
      http: true
    filters:
      volume: true
      equalizer: true
      karaoke: true
      timescale: true
      tremolo: true
      vibrato: true
      distortion: true
      rotation: true
      channelMix: true
      lowPass: true
    bufferDurationMs: 400
    frameBufferDurationMs: 5000

metrics:
  prometheus:
    enabled: false

logging:
  file:
    path: ./logs/
  level:
    root: INFO
    lavalink: INFO
EOF

echo "✅ Lavalink configuration created"

# Step 4: Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install lavalink==5.9.0

# Step 5: Create environment setup script
cat > set_java_env.sh << 'EOF'
#!/bin/bash
export JAVA_HOME=$PWD/java17
export PATH=$PWD/java17/bin:$PATH
echo "Java environment set up!"
java -version
EOF

chmod +x set_java_env.sh

echo ""
echo "🎉 Setup complete!"
echo ""
echo "📋 Next steps:"
echo "1. Run: source set_java_env.sh"
echo "2. Test Lavalink: java -jar Lavalink.jar"
echo "3. Run bot: python start_services.py"
echo ""
echo "🔧 Or run everything at once: python start_services.py" 