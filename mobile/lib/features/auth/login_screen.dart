import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../config/theme.dart';
import '../../core/services/auth_service.dart';

/// Sign-in screen — the app's front door.
///
/// Mirrors the web landing hero: the Girish Gupta avatar with a breathing maroon
/// glow, a slowly rotating dashed ring, a gentle float, and a Hinglish welcome
/// bubble, over the brand wordmark and a Google sign-in button.
class LoginScreen extends StatefulWidget {
  final AuthService authService;
  const LoginScreen({super.key, required this.authService});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> with TickerProviderStateMixin {
  static const _maroon = Color(0xFF82192A);
  static const _maroonLight = Color(0xFFC13A4B);

  bool _isLoading = false;
  String? _error;

  late final AnimationController _entrance;
  late final AnimationController _float;
  late final AnimationController _glow;
  late final AnimationController _bubbleFloat;

  @override
  void initState() {
    super.initState();
    _entrance = AnimationController(vsync: this, duration: const Duration(milliseconds: 900))
      ..forward();
    _float = AnimationController(vsync: this, duration: const Duration(milliseconds: 5500))
      ..repeat(reverse: true);
    _glow = AnimationController(vsync: this, duration: const Duration(seconds: 6))
      ..repeat(reverse: true);
    // Deliberately out of step with the avatar's float so the bubble drifts on
    // its own rhythm instead of looking glued to the portrait.
    _bubbleFloat = AnimationController(vsync: this, duration: const Duration(milliseconds: 3700))
      ..repeat(reverse: true);
  }

  @override
  void dispose() {
    _entrance.dispose();
    _float.dispose();
    _glow.dispose();
    _bubbleFloat.dispose();
    super.dispose();
  }

  Future<void> _handleGoogleSignIn() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });

    final success = await widget.authService.signInWithGoogle();

    if (!success && mounted) {
      setState(() {
        _isLoading = false;
        _error = 'Sign-in failed. Please try again.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final accent = isDark ? _maroonLight : _maroon;

    return Scaffold(
      body: DecoratedBox(
        decoration: BoxDecoration(
          // Smooth top-down wash. A radial gradient ended mid-screen and left a
          // visible arc, so this fades edge-to-edge instead.
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              Color.lerp(theme.scaffoldBackgroundColor, accent, isDark ? 0.22 : 0.12)!,
              Color.lerp(theme.scaffoldBackgroundColor, accent, isDark ? 0.07 : 0.04)!,
              theme.scaffoldBackgroundColor,
            ],
            stops: const [0.0, 0.45, 0.95],
          ),
        ),
        child: SafeArea(
          child: FadeTransition(
            opacity: CurvedAnimation(parent: _entrance, curve: Curves.easeOut),
            child: LayoutBuilder(
              builder: (context, constraints) {
                return SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(28, 8, 28, 24),
                  child: ConstrainedBox(
                    constraints: BoxConstraints(minHeight: constraints.maxHeight - 32),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        _avatarHero(context, accent),
                        const SizedBox(height: 18),
                        _wordmark(theme, accent),
                        const SizedBox(height: 26),
                        if (_error != null) _errorBox(),
                        _googleButton(theme, isDark),
                        const SizedBox(height: 14),
                        Text(
                          'By signing in, you agree to our Terms of Service',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontSize: 11.5,
                            color: theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.75),
                          ),
                        ),
                        const SizedBox(height: 8),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
        ),
      ),
    );
  }

  /// The avatar: breathing glow + rotating dashed ring + floating cut-out, with
  /// the welcome bubble tucked into the top-right.
  Widget _avatarHero(BuildContext context, Color accent) {
    final theme = Theme.of(context);
    final size = math.min(MediaQuery.of(context).size.width - 56, 340.0);

    return SizedBox(
      width: size,
      height: size,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          // Breathing radial glow
          Positioned.fill(
            child: Padding(
              padding: EdgeInsets.all(size * 0.18),
              child: AnimatedBuilder(
                animation: _glow,
                builder: (context, _) => DecoratedBox(
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: RadialGradient(
                      colors: [
                        accent.withValues(alpha: 0.20 + 0.16 * _glow.value),
                        accent.withValues(alpha: 0),
                      ],
                      stops: const [0.15, 1.0],
                    ),
                  ),
                ),
              ),
            ),
          ),
          // Soft spotlight disc behind the portrait (no hard ring — a dashed
          // outline cut straight across his face).
          Positioned.fill(
            child: Padding(
              padding: EdgeInsets.only(
                left: size * 0.08,
                right: size * 0.08,
                top: size * 0.06,
                bottom: size * 0.10,
              ),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: RadialGradient(
                    colors: [
                      accent.withValues(alpha: 0.16),
                      accent.withValues(alpha: 0.05),
                      accent.withValues(alpha: 0),
                    ],
                    stops: const [0.0, 0.62, 1.0],
                  ),
                ),
              ),
            ),
          ),
          // Floating avatar, bottom edge faded softly into the page
          Positioned.fill(
            child: AnimatedBuilder(
              animation: _float,
              builder: (context, child) => Transform.translate(
                offset: Offset(0, -12 * Curves.easeInOut.transform(_float.value)),
                child: child,
              ),
              child: Align(
                alignment: Alignment.bottomCenter,
                child: ShaderMask(
                  shaderCallback: (rect) => const LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [Colors.black, Colors.black, Colors.transparent],
                    stops: [0.0, 0.66, 0.99],
                  ).createShader(rect),
                  blendMode: BlendMode.dstIn,
                  child: Image.asset(
                    'assets/brand/hero.png',
                    height: size * 0.98,
                    fit: BoxFit.contain,
                    errorBuilder: (context, error, stack) =>
                        Icon(Icons.person, size: size * 0.5, color: accent),
                  ),
                ),
              ),
            ),
          ),
          // Welcome bubble — kept off to the right so it never covers the face,
          // and drifting gently on its own rhythm.
          Positioned(
            top: size * 0.15,
            right: -6,
            child: AnimatedBuilder(
              animation: _bubbleFloat,
              builder: (context, child) {
                final t = Curves.easeInOut.transform(_bubbleFloat.value);
                return Transform.translate(
                  offset: Offset(2.5 * t, -7 * t),
                  child: child,
                );
              },
              child: _bubble(theme, accent),
            ),
          ),
        ],
      ),
    );
  }

  Widget _bubble(ThemeData theme, Color accent) {
    return Container(
      constraints: const BoxConstraints(maxWidth: 132),
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 7),
      decoration: BoxDecoration(
        color: theme.cardColor,
        borderRadius: const BorderRadius.only(
          topLeft: Radius.circular(12),
          topRight: Radius.circular(12),
          bottomRight: Radius.circular(12),
          bottomLeft: Radius.circular(3),
        ),
        border: Border.all(color: accent.withValues(alpha: 0.3)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.18),
            blurRadius: 14,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 6,
            height: 6,
            margin: const EdgeInsets.only(top: 4, right: 6),
            decoration: BoxDecoration(color: accent, shape: BoxShape.circle),
          ),
          Flexible(
            child: Text(
              'Namaskar! Aapka swagat hai 🙏',
              style: TextStyle(
                fontSize: 10,
                height: 1.3,
                color: theme.colorScheme.onSurface,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _wordmark(ThemeData theme, Color accent) {
    return Column(
      children: [
        Text(
          'StockSage',
          style: theme.textTheme.displaySmall?.copyWith(
            fontSize: 38,
            fontWeight: FontWeight.w800,
            letterSpacing: -1,
          ),
        ),
        Text(
          'INDIA',
          style: TextStyle(
            fontSize: 26,
            fontWeight: FontWeight.w800,
            letterSpacing: 10,
            color: accent,
          ),
        ),
        const SizedBox(height: 10),
        Text(
          'by Girish Gupta',
          style: TextStyle(
            fontSize: 10.5,
            fontWeight: FontWeight.w600,
            letterSpacing: 1.8,
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          'NSE & BSE stock analysis, live charts and your AI market guide.',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: 13,
            height: 1.45,
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
      ],
    );
  }

  Widget _errorBox() {
    return Container(
      padding: const EdgeInsets.all(12),
      margin: const EdgeInsets.only(bottom: 14),
      decoration: BoxDecoration(
        color: AppTheme.errorColor.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppTheme.errorColor.withValues(alpha: 0.3)),
      ),
      child: Row(
        children: [
          const Icon(Icons.error_outline, color: AppTheme.errorColor, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text(_error!, style: const TextStyle(color: AppTheme.errorColor, fontSize: 13)),
          ),
        ],
      ),
    );
  }

  Widget _googleButton(ThemeData theme, bool isDark) {
    return SizedBox(
      width: double.infinity,
      height: 54,
      child: ElevatedButton(
        onPressed: _isLoading ? null : _handleGoogleSignIn,
        style: ElevatedButton.styleFrom(
          backgroundColor: isDark ? const Color(0xFF18181B) : Colors.white,
          foregroundColor: isDark ? Colors.white : const Color(0xFF291012),
          elevation: 0,
          side: BorderSide(color: theme.dividerColor),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(15)),
        ),
        child: _isLoading
            ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2))
            : Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  SvgPicture.string(_googleG, width: 20, height: 20),
                  const SizedBox(width: 12),
                  const Text(
                    'Continue with Google',
                    style: TextStyle(fontSize: 15.5, fontWeight: FontWeight.w600),
                  ),
                ],
              ),
      ),
    );
  }

  /// Google's "G" mark, inlined so the button needs no network fetch.
  static const String _googleG = '''
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">
  <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
  <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
  <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24s.92 7.54 2.56 10.78l7.97-6.19z"/>
  <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
</svg>''';
}
