import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

/// StockSage AI mascot — a serene sage bust in line art.
///
/// Ported from the web app's sage icon. Main strokes take [color] (defaults to
/// the current icon theme colour); the eyes and sash use the maroon accent so
/// the mascot stays on-brand in both light and dark themes.
class SageIcon extends StatelessWidget {
  final double size;
  final Color? color;
  final Color accent;
  final double strokeWidth;

  const SageIcon({
    super.key,
    this.size = 24,
    this.color,
    this.accent = const Color(0xFF82192A), // brand maroon
    this.strokeWidth = 1.6,
  });

  @override
  Widget build(BuildContext context) {
    final stroke = _hex(color ?? IconTheme.of(context).color ?? Colors.white);
    final acc = _hex(accent);
    final svg = '''
<svg xmlns="http://www.w3.org/2000/svg" width="$size" height="$size" viewBox="0 0 24 24"
     fill="none" stroke="$stroke" stroke-width="$strokeWidth"
     stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="3.5" r="1.4" />
  <path d="M10.7 5c.8-.5 1.8-.5 2.6 0" />
  <path d="M8 9C7.9 6.4 9.6 4.6 12 4.6S16.1 6.4 16 9" />
  <path d="M8 9c-.3 2 0 4 1.2 5.4.9 1 1.8 1.5 2.8 1.5s1.9-.5 2.8-1.5C16 13 16.3 11 16 9" />
  <path d="M9.6 10q.75.6 1.5 0" stroke="$acc" />
  <path d="M12.9 10q.75.6 1.5 0" stroke="$acc" />
  <path d="M4.7 21c.3-3.2 2.7-5.4 5.5-5.6" />
  <path d="M19.3 21c-.3-3.2-2.7-5.4-5.5-5.6" />
  <path d="M9.4 16 16.6 20.8" stroke="$acc" />
</svg>''';
    return SvgPicture.string(svg, width: size, height: size);
  }

  static String _hex(Color c) =>
      '#${(c.toARGB32() & 0xFFFFFF).toRadixString(16).padLeft(6, '0')}';
}
