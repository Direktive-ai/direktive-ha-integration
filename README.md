<table>
  <tr>
    <td width="127"><img src="https://cdn.discordapp.com/icons/1397167613506748468/3647df6e0f15b5322003ce556a809e7a.png?size=160&quality=lossless" alt="LOGO" ></td>
    <td><h1>Direktive.ai - Home Assistant Integration</h1></td>
  </tr>
</table>
<table>
  <tr>
    <td width="250">
      <a aria-label="@DIREKTIVE-AI/HA-INTEGRATION" href="https://github.com/Direktive-ai/direktive-ha-integration" width="250">
        <img alt="" src="https://img.shields.io/badge/DIREKTIVE--AI/INTEGRATION-V0.9.0-blue?style=for-the-badge&labelColor=10131a&color=1EAEDB" align="center">
      </a>
    </td>
    <td width="250">
      <a aria-label="@DIREKTIVE-AI/HA-LOVELACE" href="https://github.com/Direktive-ai/direktive-ha-lovlace">
        <img alt="" src="https://img.shields.io/badge/DIREKTIVE--AI/LOVELACE-V0.9.0-blue?style=for-the-badge&labelColor=10131a&color=1EAEDB" align="center">
      </a>
    </td>
    <td width="210">
      <a aria-label="Join the community on Discord" href="https://discord.gg/4M4ARJhz">
        <img alt="" src="https://img.shields.io/badge/Join%20the%20Discord-blueviolet.svg?style=for-the-badge&labelColor=10131a&logo=Discord&logoWidth=20&color=9b87f5" align="center">
      </a>
    </td>
  </tr>
</table>

## Simplify your [Home Assistant](https://www.home-assistant.io/) Automation creation
Our primary goal at Direktive.ai is to greatly simplify the creation of Home Assistant automations (called Direktives) by leveraging AI and creating an ecosystem that allows users to talk to their installation. With this we hope to:

##### Lower the entry barrier for Home Assistant adoption for new installations by simplifying interactions. Ultimately, lower the complexity for smart home adoption in the general population altogether

##### Allow anyone in the house to create new automations

##### Easier to create & manager automations = more automations = smarter houses

##### Create a solid foundation for new features and possibilities (currently in develoment), such as vision-powered automations, automation suggestion, etc

## What is this Integration for?
This integration is the piece of the puzzle that will connect your Home Assistant instalation with our cloud services. Similar to an Alexa or a Google integration, it allows you to choose which devices are exposed, with maximum security, and to be the middleman between your house an Direktive.ai's brain where the magic really happens.

#### Our entire ecosystem has been designed with a seurity-first mindset. Check our <a href="https://direktive.ai/security">security section</a> in our website to understand better how we protect your data from everyone, including ourselves.

## Get Started

### Prerequisites
- A Home Assistant instance (version 2023.8 or later recommended)
- An account on [Direktive.ai](https://direktive.ai) (join our [Alpha track](https://direktive.ai/apply-for-alpha) for free access)
- [HACS](https://hacs.xyz/) installed (recommended) or manual installation capability

### Installation

#### Option 1: HACS Installation (Recommended)
1. Make sure you have [HACS](https://hacs.xyz/) installed in your Home Assistant instance
2. Add this as a custom repository in HACS (Copy-paste this repository link and select "Integration")
3. Go to **HACS** → **Integrations** → **Add Integration**
4. Click the **+** button in the bottom right corner
5. Search for "Direktive.ai" and select it
6. Click **Download**
7. Restart Home Assistant

#### Option 2: Manual Installation
1. Download the integration files from this repository
2. Place the files in your Home Assistant configuration directory:
   ```
   your-config-dir/custom_components/direktive/
   ```
3. Restart Home Assistant

### Configuration

1. Navigate to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for "Direktive.ai" and select it
4. Enter your configuration details:
   - **API Key**: Found in your [Direktive.ai Profile](https://direktive.ai/profile) after logging in
   - **Home Assistant URL**: The HTTPS address of your Home Assistant instance
   - **Entities to Expose**: Select which entities you want to expose to Direktive.ai

### Entity Selection
For the time being, we don't automatically expose all entities within a device. You'll need to manually select the entities that you want to:
- Receive state updates from
- Allow the service to trigger actions on

**Supported Entity Types During Alpha:**
- Lights
- Shutters/Blinds
- Sensors
- Switches

#### Devices are composed by multiple entities, make sure you select the one that will expose the states that you need.
Example: If you need to detect motion, you'll need to expose the entity that has the motion state, not the battery, light, vibration, etc.


## Troubleshooting

### Common Issues
- **Integration not appearing**: Make sure you've restarted Home Assistant after installation
- **Connection failed**: Verify your API key and Home Assistant URL
- **Entities not working**: Ensure the selected entities are properly configured and accessible

### Getting Help
- Join our [Discord community](https://discord.gg/SsSvYbrp2J) for support
- Check our [documentation](https://direktive.ai/docs) for detailed guides
- Report issues on our [GitHub repository](https://github.com/Direktive-ai/direktive-ha-integration)

## FAQ

### Do I need to pay for this?
During the Alpha track, Direktive.ai is completely free. Apply for our [Alpha program](https://direktive.ai/apply-for-alpha) to get 100% discount during checkout.

### Is my data secure?
Yes, we take security seriously. All data is encrypted in transit and at rest. We use industry-standard security practices and regularly update our security measures. You can read more on our [security page](https://direktive.ai/security).

### Is there a risk of someone controlling my house?
No. You have complete control over which entities are exposed, and you can revoke access at any time. The integration only has access to the specific entities you choose to expose.

### Can I cancel this at any time?
Yes, you can cancel your subscription at any time. We offer a 30-day money-back guarantee if you're not satisfied with our service.

### What stage is this product on right now?
We're currently in Alpha stage, focusing on core functionality with a limited set of devices and entity types. Our main focus is on Lights, Shutters, Sensors, and Switches during this phase.

### What other features are we working on now?
We're developing vision-powered automations, automation suggestions, and expanding device support. Our roadmap includes more advanced AI capabilities and broader device compatibility.

## Website
Want to join our Alpha track before we go live? Check us out at [Direktive.ai](https://direktive.ai) or on our [Discord Channel](https://discord.gg/SsSvYbrp2J). Reach out for suggestions, questions, feature requests or bugs!

## Contributing
We welcome contributions! Please feel free to submit issues, feature requests, or pull requests to help improve this integration.

## License
This project is licensed under the MIT License - see the LICENSE file for details.