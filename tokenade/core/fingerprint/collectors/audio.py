"""
Audio Collector - Collects AudioContext fingerprint.
"""

from typing import Dict, Any
from .base import BaseCollector


class AudioCollector(BaseCollector):
    """Collects AudioContext fingerprint data."""

    @property
    def api_name(self) -> str:
        return "audio"

    def collect(self, browser_manager) -> Dict[str, Any]:
        """Collect audio fingerprint."""
        script = """() => {
            try {
                const AudioContext = window.AudioContext || window.webkitAudioContext;
                if (!AudioContext) return {};

                const ctx = new AudioContext();
                const oscillator = ctx.createOscillator();
                const analyser = ctx.createAnalyser();
                const gain = ctx.createGain();

                oscillator.connect(analyser);
                analyser.connect(gain);
                gain.connect(ctx.destination);

                oscillator.type = 'triangle';
                oscillator.frequency.value = 10000;

                gain.gain.value = 0;
                oscillator.start(0);

                const fftSize = analyser.fftSize;
                const buffer = new Uint8Array(fftSize);
                analyser.getByteFrequencyData(buffer);

                const hash = buffer.slice(0, 50).join(',');

                oscillator.stop();
                ctx.close();

                return {
                    sampleRate: ctx.sampleRate,
                    channelCount: ctx.destination.channelCount,
                    channelCountMode: ctx.destination.channelCountMode,
                    fftSize: fftSize,
                    hash: hash
                };
            } catch(e) {
                return {};
            }
        }"""

        try:
            result = browser_manager.evaluate(script)
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}

    def get_script_template(self) -> str:
        return """
// Audio spoofing
(function() {
    const sampleRate = {{sampleRate}};
    const channelCount = {{channelCount}};
    const channelCountMode = "{{channelCountMode}}";
    const fftSize = {{fftSize}};
    const audioHash = "{{hash}}";

    const origAudioContext = window.AudioContext || window.webkitAudioContext;
    if (!origAudioContext) return;

    window.AudioContext = function() {
        const ctx = new origAudioContext();

        // Override sample rate
        Object.defineProperty(ctx, 'sampleRate', {
            get: function() { return sampleRate; },
            configurable: true
        });

        // Override destination
        if (ctx.destination) {
            Object.defineProperty(ctx.destination, 'channelCount', {
                get: function() { return channelCount; },
                configurable: true
            });
            Object.defineProperty(ctx.destination, 'channelCountMode', {
                get: function() { return channelCountMode; },
                configurable: true
            });
        }

        // Override analyser
        const origCreateAnalyser = ctx.createAnalyser;
        ctx.createAnalyser = function() {
            const analyser = origCreateAnalyser.call(ctx);
            Object.defineProperty(analyser, 'fftSize', {
                get: function() { return fftSize; },
                configurable: true
            });

            const origGetByteFrequencyData = analyser.getByteFrequencyData;
            analyser.getByteFrequencyData = function(array) {
                // Fill with pre-computed hash data
                const hashData = audioHash.split(',').map(Number);
                for (let i = 0; i < Math.min(array.length, hashData.length); i++) {
                    array[i] = hashData[i];
                }
                return array;
            };

            return analyser;
        };

        return ctx;
    };
})();
"""
