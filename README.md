# Puddles Discord Bot 🦆

A Discord bot that sends random duck images and stays online 24/7 on Replit!

## Features

- `/quack` command: Sends a random duck image
- 24/7 uptime using Flask server and UptimeRobot

## Setup Instructions

1. Create a new Discord application and bot at [Discord Developer Portal](https://discord.com/developers/applications)
2. Get your bot token and keep it safe
3. Create a new Replit project and upload these files
4. Add your bot token to Replit's Secrets (Environment variables) with the key name `TOKEN`
5. Install the required packages using the package manager in Replit
6. Run the bot!

## Setting Up 24/7 Uptime

1. Create an account at [UptimeRobot](https://uptimerobot.com/)
2. Add a new monitor:
   - Select "HTTP(s)"
   - Set monitor type to "HTTP(s)"
   - Name it whatever you like
   - Set the URL to your Replit project URL (will look like: https://your-repl-name.your-username.repl.co)
   - Set checking interval to 5 minutes

## Commands

- `/quack`: Sends a random duck image from the random-d.uk API

## Credits

- Duck images provided by [random-d.uk](https://random-d.uk/)