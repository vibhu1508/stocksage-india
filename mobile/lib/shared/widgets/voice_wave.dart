import 'dart:math' as math;
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

/// A live voice waveform — bars that ripple continuously and grow with the
/// current mic loudness ([level], 0..1). Used while recording so the user can
/// see their voice is being picked up.
class VoiceWave extends StatefulWidget {
  final ValueListenable<double> level;
  final Color color;
  final int bars;
  final double height;

  const VoiceWave({
    super.key,
    required this.level,
    required this.color,
    this.bars = 24,
    this.height = 36,
  });

  @override
  State<VoiceWave> createState() => _VoiceWaveState();
}

class _VoiceWaveState extends State<VoiceWave> with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 900))
      ..repeat();
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: widget.height,
      width: double.infinity,
      child: AnimatedBuilder(
        animation: Listenable.merge([_ctrl, widget.level]),
        builder: (context, child) => CustomPaint(
          painter: _WavePainter(
            phase: _ctrl.value * 2 * math.pi,
            level: widget.level.value,
            color: widget.color,
            bars: widget.bars,
          ),
        ),
      ),
    );
  }
}

class _WavePainter extends CustomPainter {
  final double phase;
  final double level;
  final Color color;
  final int bars;

  _WavePainter({
    required this.phase,
    required this.level,
    required this.color,
    required this.bars,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..strokeCap = StrokeCap.round
      ..strokeWidth = 3;

    final gap = size.width / bars;
    final midY = size.height / 2;
    // A gentle floor so bars are visible even in silence, plus a loudness-driven swell.
    final amp = (0.12 + level * 0.88) * (size.height / 2);

    for (var i = 0; i < bars; i++) {
      final x = gap * i + gap / 2;
      final wobble = math.sin(phase + i * 0.6);
      final h = (0.25 + 0.75 * ((wobble + 1) / 2)) * amp;
      canvas.drawLine(Offset(x, midY - h), Offset(x, midY + h), paint);
    }
  }

  @override
  bool shouldRepaint(_WavePainter old) =>
      old.phase != phase || old.level != level || old.color != color;
}
