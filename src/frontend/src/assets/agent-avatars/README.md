# AI Agent Avatars

This directory contains SVG icons that are used as avatars for AI Agents in the application.

## Using Avatars

The avatars in this directory can be selected when creating a new AI Agent. The avatar selection is integrated into the `CreateAIAgentComponent`.

## Adding New Avatars

To add new avatars:

1. Create a new SVG file in this directory following the naming pattern of existing avatars
2. Update the `AGENT_AVATARS` array in `src/frontend/src/modals/templatesModal/components/CreateGuidedAIAgentComponent/index.tsx` to include your new avatar
3. Import the new SVG file at the top of the component

## Avatar Design Guidelines

When creating new avatars, follow these guidelines:

- Use 64x64 pixel SVG format
- Use colors that work well in both light and dark themes
- Create simple, recognizable designs
- Provide good visual contrast between background and foreground elements
- Test your avatar in both light and dark mode

## Current Avatars

- `robot.svg` - A robot-style avatar
- `assistant.svg` - A personal assistant avatar
- `scientist.svg` - A scientist/researcher avatar
- `researcher.svg` - A research-focused avatar
- `teacher.svg` - An education-focused avatar

Each avatar has a unique style and color scheme to help users differentiate between different AI Agents. 