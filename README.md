# NestQuest - House Chaos Coordination

Home Assistant custom integration for managing chores, custody schedules, and house coordination.

## Overview

NestQuest helps households coordinate daily life, chore tracking, custody schedules, and shared tasks directly within Home Assistant. It provides sensors, calendar events, and service calls designed for busy households and modern co-parenting setups.

## Installation

### HACS Installation (Recommended)

1. Ensure [HACS (Home Assistant Community Store)](https://hacs.xyz/) is installed.
2. In Home Assistant, open **HACS** > **Integrations**.
3. Select the three-dots menu in the top right and click **Custom repositories**.
4. Enter the repository URL: `https://github.com/talon2king/NestQuest`
5. Select category **Integration** and click **Add**.
6. Search for **NestQuest** and click **Download**.
7. Restart Home Assistant.

> **Note:** Development happens in the private Gitea repository
> (`https://code.cubecraftlabs.com/Maniacs_Mansion/NestQuest`). The GitHub
> repository is a public mirror maintained for HACS distribution.

### Manual Installation

1. Download the latest release from the repository.
2. Copy the `custom_components/nestquest` directory into your Home Assistant installation's `config/custom_components/` folder:
   ```bash
   cp -R custom_components/nestquest <config_dir>/custom_components/
   ```
3. Restart Home Assistant.

## Configuration

After installation and restart:
1. Navigate to **Settings** > **Devices & Services** in Home Assistant.
2. Click **Add Integration** and search for **NestQuest**.
3. Follow the on-screen configuration flow.

## Developer Setup and Testing

This project uses [`uv`](https://github.com/astral-sh/uv) for fast Python package and dependency management.

### Prerequisites

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/) installed on your machine

### Setup Environment

To set up the development environment and install dependencies:

```bash
uv sync
```

### Running Tests

Run the test suite with `pytest`:

```bash
uv run pytest
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
