"""
Behavioral signal injection.

Generates human-like mouse movements, scroll patterns, and click timing
to bypass behavioral analysis detection.
"""

import math
import random
import logging
from typing import List, Tuple, Dict

logger = logging.getLogger(__name__)


class BehavioralInjector:
    """Generate human-like behavioral signals."""

    @staticmethod
    def generate_mouse_path(start: Tuple[int, int], end: Tuple[int, int],
                            steps: int = None) -> List[Dict]:
        """Generate a human-like mouse movement path using Bezier curves.

        Returns list of {x, y, delay_ms} dicts.
        Uses cubic Bezier with random control points for natural curves.
        """
        if steps is None:
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            distance = math.sqrt(dx * dx + dy * dy)
            steps = max(10, min(100, int(distance / 5)))

        # Random control points for cubic Bezier
        cp1_x = start[0] + (end[0] - start[0]) * random.uniform(0.2, 0.4) + random.randint(-30, 30)
        cp1_y = start[1] + (end[1] - start[1]) * random.uniform(0.1, 0.3) + random.randint(-30, 30)
        cp2_x = start[0] + (end[0] - start[0]) * random.uniform(0.6, 0.8) + random.randint(-30, 30)
        cp2_y = start[1] + (end[1] - start[1]) * random.uniform(0.7, 0.9) + random.randint(-30, 30)

        path = []
        for i in range(steps + 1):
            t = i / steps
            # Cubic Bezier formula
            u = 1 - t
            x = u ** 3 * start[0] + 3 * u ** 2 * t * cp1_x + 3 * u * t ** 2 * cp2_x + t ** 3 * end[0]
            y = u ** 3 * start[1] + 3 * u ** 2 * t * cp1_y + 3 * u * t ** 2 * cp2_y + t ** 3 * end[1]

            # Add small jitter for realism
            x += random.gauss(0, 0.5)
            y += random.gauss(0, 0.5)

            # Delay: faster in middle, slower at start/end (ease-in-out)
            if t < 0.1 or t > 0.9:
                delay = random.randint(8, 20)
            else:
                delay = random.randint(2, 8)

            path.append({
                "x": round(x, 2),
                "y": round(y, 2),
                "delay_ms": delay,
            })

        return path

    @staticmethod
    def generate_scroll_pattern(distance: int) -> List[Dict]:
        """Generate human-like scroll pattern.

        Returns list of {delta_y, delay_ms} dicts.
        Uses ease-out curve (fast start, slow end).
        """
        if distance <= 0:
            return []

        steps = max(3, distance // 50)
        pattern = []
        remaining = distance

        for i in range(steps):
            # Ease-out: large scroll at start, smaller at end
            progress = i / max(1, steps - 1)
            ease_factor = 1.0 - progress

            # Scroll amount decreases as we go
            scroll_amount = int(remaining * ease_factor / (steps - i))
            scroll_amount = max(10, min(scroll_amount, remaining))

            # Add some randomness
            scroll_amount = int(scroll_amount * random.uniform(0.8, 1.2))
            scroll_amount = min(scroll_amount, remaining)

            # Delay: longer pauses between scrolls as we slow down
            base_delay = int(30 + 100 * progress)
            delay = random.randint(max(20, base_delay - 20), base_delay + 30)

            pattern.append({
                "delta_y": scroll_amount,
                "delay_ms": delay,
            })

            remaining -= scroll_amount
            if remaining <= 0:
                break

        # Add final small scroll if we didn't reach the target
        if remaining > 0:
            pattern.append({
                "delta_y": remaining,
                "delay_ms": random.randint(100, 200),
            })

        return pattern

    @staticmethod
    def generate_click_timing() -> int:
        """Generate realistic click delay in milliseconds.

        Uses Gaussian distribution centered around 150ms with std dev of 50ms.
        """
        delay = int(random.gauss(150, 50))
        # Clamp to realistic range
        return max(50, min(400, delay))

    @staticmethod
    def get_stealth_inject_script() -> str:
        """Return JavaScript to inject behavioral hooks into the page.

        Hooks mouse event listeners to add realistic timing jitter.
        """
        return """
        // Add subtle randomness to mouse event timing
        const originalDispatchEvent = Event.prototype.dispatchEvent;
        Event.prototype.dispatchEvent = function(event) {
            if (event instanceof MouseEvent) {
                const jitter = Math.random() * 2 - 1; // -1 to 1 ms
                event.timeStamp += jitter;
            }
            return originalDispatchEvent.call(this, event);
        };
        """
