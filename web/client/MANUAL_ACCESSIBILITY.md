# Xiel manual accessibility checklist

Run this checklist against the production build after automated tests pass.

## Keyboard and focus

- Tab from the browser chrome and confirm the skip link is the first page control.
- Open and close the mobile navigation using Enter, Space, Escape, and the backdrop.
- Confirm focus stays inside the open navigation and returns to the trigger on close.
- Navigate every client route and confirm the page heading receives focus without a surprise scroll.
- Complete every form and confirmation without a pointer.

## Screen readers

- NVDA + Firefox: review headings, landmarks, links, form labels, live status, validation, and destructive confirmations.
- VoiceOver + Safari: repeat the route, dashboard, settings, economy, and privileged-console flows.
- Confirm repeated guild and destructive actions include their object name in the accessible label.
- Confirm the decorative Saturn hero media is absent from the accessibility tree and does not create an extra keyboard stop.

## Visual access

- Test Windows forced-colors mode and verify every state remains visible without color alone.
- Test 200% and 400% zoom at 320, 360, 680, 720, 1000, and 1440 CSS pixels.
- Verify normal text reaches 4.5:1 contrast and large text, focus indicators, controls, and meaningful boundaries reach 3:1.
- Enable reduced motion at runtime and confirm the Saturn hero uses its static poster, no Saturn video is requested, and all continuous, staggered, parallax, smooth-scroll, and spinner motion stops.
- Enable data saver and confirm the Saturn hero uses the same static poster instead of loading or playing video.

Record browser/assistive-technology versions, failures, and the retest result alongside the release.
