// Copyright (c) 2025 Tao Energy SRL. Licensed under the MIT License.
// SeaCommons: deterministic, O(N) per-symbol dual-tone detector.
namespace TAOSW.DSC_Decoder.Core
{
    public class FSKDetector
    {
        private readonly int _sampleRate;
        private int _cachedLength;
        private float[] _window = Array.Empty<float>();
        private float _leftFrequency = float.NaN;
        private float _rightFrequency = float.NaN;
        private double _leftCoefficient;
        private double _rightCoefficient;

        public FSKDetector(int sampleRate)
        {
            if (sampleRate <= 0) throw new ArgumentOutOfRangeException(nameof(sampleRate));
            _sampleRate = sampleRate;
        }

        public int DetectFSK(float[] inSignal, float leftFreq, float rightFreq, out double degreeOfCertainty)
        {
            if (inSignal is null || inSignal.Length < 4)
                throw new ArgumentException("FSK window is too small", nameof(inSignal));
            if (!float.IsFinite(leftFreq) || !float.IsFinite(rightFreq) ||
                leftFreq <= 0 || rightFreq <= 0 ||
                leftFreq >= _sampleRate / 2f || rightFreq >= _sampleRate / 2f)
                throw new ArgumentOutOfRangeException(nameof(leftFreq), "Invalid FSK tone frequencies");

            // Cached Hann weights and Goertzel recurrence coefficients.
            // DSC: 100 baud / 12 kHz -> 120 samples/bit. The old implementation
            // performed three separate 2048-point FFTs *per bit* with a large
            // zero-padded window and quantized the tone frequencies to bins.
            // Goertzel evaluates the exact 1615/1785 Hz tones in O(N) time.
            if (_cachedLength != inSignal.Length)
            {
                _cachedLength = inSignal.Length;
                _window = new float[_cachedLength];
                for (int i = 0; i < _cachedLength; i++)
                    _window[i] = 0.5f * (1 - MathF.Cos(2 * MathF.PI * i / (_cachedLength - 1)));
            }
            if (_leftFrequency != leftFreq || _rightFrequency != rightFreq)
            {
                _leftFrequency = leftFreq;
                _rightFrequency = rightFreq;
                _leftCoefficient = 2 * Math.Cos(2 * Math.PI * leftFreq / _sampleRate);
                _rightCoefficient = 2 * Math.Cos(2 * Math.PI * rightFreq / _sampleRate);
            }
            double leftOne = 0, leftTwo = 0, rightOne = 0, rightTwo = 0;
            for (int i = 0; i < inSignal.Length; i++)
            {
                double sample = inSignal[i] * _window[i];
                double leftNext = sample + _leftCoefficient * leftOne - leftTwo;
                double rightNext = sample + _rightCoefficient * rightOne - rightTwo;
                leftTwo = leftOne;
                leftOne = leftNext;
                rightTwo = rightOne;
                rightOne = rightNext;
            }
            double leftPower = Math.Max(0, leftOne * leftOne + leftTwo * leftTwo - _leftCoefficient * leftOne * leftTwo);
            double rightPower = Math.Max(0, rightOne * rightOne + rightTwo * rightTwo - _rightCoefficient * rightOne * rightTwo);
            double maximum = Math.Max(leftPower, rightPower);
            degreeOfCertainty = maximum <= 1e-15 ? 0 : Math.Min(1, Math.Abs(leftPower - rightPower) / maximum);
            // Preserve TAOSW's existing mark/space bit convention.
            return leftPower < rightPower ? 0 : 1;
        }
    }
}
