# Fresh Fruits Market - Cross-Platform Deployment Guide

## Overview

Fresh Fruits Market can be deployed on Windows, Linux, and macOS - see section below.

## System Requirements

- **OS**: Windows 8/10/11, Linux (Ubuntu 18.04+), macOS 10.14+
- **RAM**: 4GB minimum
- **Storage**: 500MB free space
- **Database**: MongoDB 4.4+ (must be installed separately)

## Quick Start

### Option 1: Pre-built Executables (Recommended for End Users)

Download the appropriate executable for your OS:

| Platform | File | Size |
|----------|------|------|
| Windows | `FreshFruitsMarket.exe` | ~15MB |
| Linux | `FreshFruitsMarket` | ~12MB |
| macOS | `FreshFruitsMarket.app` | ~18MB |

**Steps:**
1. Download the executable
2. Install MongoDB (see MongoDB Setup below)
3. Double-click to run

### Option 2: Python Source (For Developers)

```bash
# Install Python 3.8+ and MongoDB
git clone <repository-url>
cd FreshFruitsMarket
pip install -r requirements.txt
python marketreceipt.py
```

## MongoDB Setup (Required for all platforms)

### Windows
1. Download MongoDB Community Server from https://www.mongodb.com/try/download/community
2. Run installer with "Install MongoDB as a Service" checked
3. MongoDB will start automatically

### Linux (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install mongodb
sudo systemctl start mongodb
sudo systemctl enable mongodb
```

### macOS
```bash
brew tap mongodb/brew
brew install mongodb-community
brew services start mongodb-community
```

## Building from Source

### Windows
```batch
build.bat
```
Output: `dist/FreshFruitsMarket.exe`

### Linux/macOS
```bash
chmod +x build.sh
./build.sh
```
Output: `dist/FreshFruitsMarket`

## Docker Deployment (Advanced)

For containerized deployment with MongoDB included:

```bash
docker-compose up -d
```

**Note:** This is a desktop GUI application. The Docker setup provides a containerized MongoDB. To run the GUI app, use:
- The Python source option (for developers)
- The pre-built executable (for end users)

## Troubleshooting

### "MongoDB connection error"
- Ensure MongoDB service is running
- Check firewall settings (port 27017)
- Verify `mongod` process is active

### "Executable won't start"
- Windows: Install Visual C++ Redistributable
- Linux: `chmod +x FreshFruitsMarket`
- macOS: Right-click > Open (bypass Gatekeeper)

### "GUI is blank"
- Update graphics drivers
- Try running from terminal to see errors

## Distribution Checklist

When packaging for users, include:
- [ ] Executable file
- [ ] README.md
- [ ] MongoDB installation guide
- [ ] Sample data initialization script (optional)

## Support

For issues or questions:
- Check MongoDB is running: `mongod --version`
- Test Python installation: `python --version`
- View logs: Run from terminal/command prompt
