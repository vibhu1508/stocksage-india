import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/services/ai_chat_service.dart';
import '../../core/services/voice_service.dart';
import '../../shared/widgets/sage_icon.dart';
import '../../shared/widgets/voice_wave.dart';

/// StockSage AI — the conversational assistant.
///
/// English / Hindi / Hinglish, voice in & out, live market data, news and
/// portfolio bookkeeping. Market information & education only — never advice.
class AiAssistantScreen extends StatefulWidget {
  const AiAssistantScreen({super.key});

  @override
  State<AiAssistantScreen> createState() => _AiAssistantScreenState();
}

class _AiAssistantScreenState extends State<AiAssistantScreen> {
  static const disclaimerEn =
      'StockSage AI provides market information and education only — not financial advice. '
      'We do not recommend buying or selling any security. Please consult your financial advisor before making any decisions.';
  static const disclaimerHi =
      'StockSage AI केवल बाज़ार की जानकारी और शिक्षा देता है — यह वित्तीय सलाह नहीं है। '
      'हम किसी भी शेयर को खरीदने या बेचने की सलाह नहीं देते। कोई भी निर्णय लेने से पहले कृपया अपने वित्तीय सलाहकार से परामर्श करें।';

  static const _suggestions = [
    'Reliance ka price kya hai?',
    'Aaj market kaisa hai?',
    'TCS ki latest news',
    'निफ्टी आज कैसा है?',
  ];

  final AiChatService _chat = AiChatService();
  final VoiceService _voice = VoiceService();
  final TextEditingController _input = TextEditingController();
  final ScrollController _scroll = ScrollController();

  bool _voiceReplies = false;
  String _lastSpoken = '';

  @override
  void initState() {
    super.initState();
    _chat.addListener(_onChat);
    _voice.addListener(_onVoice);
  }

  @override
  void dispose() {
    _chat.removeListener(_onChat);
    _voice.removeListener(_onVoice);
    _chat.dispose();
    _voice.dispose();
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _onChat() {
    if (!mounted) return;
    setState(() {});
    _scrollToBottom();
    // Read out each completed assistant reply when voice replies are on.
    if (!_voiceReplies || _chat.messages.isEmpty) return;
    final last = _chat.messages.last;
    if (!last.isUser && !last.streaming && last.text.isNotEmpty && last.text != _lastSpoken) {
      _lastSpoken = last.text;
      _voice.speak(last.text);
    }
  }

  void _onVoice() {
    if (mounted) setState(() {});
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(
          _scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Color _maroon(BuildContext context) =>
      Theme.of(context).brightness == Brightness.dark ? const Color(0xFFC13A4B) : const Color(0xFF82192A);

  void _sendCurrent() {
    final text = _input.text.trim();
    if (text.isEmpty) return;
    _input.clear();
    _chat.send(text);
  }

  Future<void> _toggleMic() async {
    if (_voice.recording) {
      final text = await _voice.stopRecording();
      if (text.isNotEmpty) {
        _input.text = text;
        _sendCurrent();
      } else if (mounted) {
        _snack('Kuch sunai nahi diya. Dobara try karein.');
      }
    } else {
      await _voice.startRecording(onError: (m) => _snack(m));
    }
  }

  void _snack(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(msg), behavior: SnackBarBehavior.floating),
    );
  }

  void _showDisclaimer() {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Row(
          children: [
            Icon(LucideIcons.info, size: 18, color: _maroon(ctx)),
            const SizedBox(width: 8),
            const Text('Disclaimer'),
          ],
        ),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: const [
              Text(disclaimerEn, style: TextStyle(fontSize: 13, height: 1.5)),
              SizedBox(height: 12),
              Text(disclaimerHi, style: TextStyle(fontSize: 13, height: 1.6)),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('OK')),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final maroon = _maroon(context);

    return Scaffold(
      appBar: AppBar(
        titleSpacing: 0,
        title: Row(
          children: [
            Container(
              width: 34,
              height: 34,
              decoration: BoxDecoration(
                color: maroon.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(10),
              ),
              alignment: Alignment.center,
              child: SageIcon(size: 22, color: theme.colorScheme.onSurface, accent: maroon),
            ),
            const SizedBox(width: 10),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text('StockSage AI', style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
                Text(
                  'Market info & education only',
                  style: TextStyle(fontSize: 11, color: theme.colorScheme.onSurfaceVariant),
                ),
              ],
            ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: _voiceReplies ? 'Voice replies on' : 'Voice replies off',
            icon: Icon(_voiceReplies ? LucideIcons.volume2 : LucideIcons.volumeX,
                color: _voiceReplies ? maroon : theme.colorScheme.onSurfaceVariant),
            onPressed: () {
              setState(() => _voiceReplies = !_voiceReplies);
              if (!_voiceReplies) _voice.stopSpeaking();
            },
          ),
          IconButton(
            tooltip: 'Disclaimer',
            icon: Icon(LucideIcons.info, color: theme.colorScheme.onSurfaceVariant),
            onPressed: _showDisclaimer,
          ),
        ],
      ),
      body: Column(
        children: [
          _disclaimerBanner(context),
          Expanded(
            child: _chat.messages.isEmpty
                ? _emptyState(context)
                : ListView.builder(
                    controller: _scroll,
                    padding: const EdgeInsets.fromLTRB(12, 12, 12, 12),
                    itemCount: _chat.messages.length,
                    itemBuilder: (_, i) => _messageBubble(context, _chat.messages[i]),
                  ),
          ),
          _inputBar(context),
        ],
      ),
    );
  }

  Widget _disclaimerBanner(BuildContext context) {
    final theme = Theme.of(context);
    final maroon = _maroon(context);
    return Container(
      width: double.infinity,
      color: maroon.withValues(alpha: 0.08),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(LucideIcons.shieldCheck, size: 15, color: maroon),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              'Market information & education only — not financial advice. '
              'बाज़ार की जानकारी व शिक्षा — वित्तीय सलाह नहीं।',
              style: TextStyle(fontSize: 11.5, height: 1.4, color: theme.colorScheme.onSurfaceVariant),
            ),
          ),
        ],
      ),
    );
  }

  Widget _emptyState(BuildContext context) {
    final theme = Theme.of(context);
    final maroon = _maroon(context);
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        const SizedBox(height: 24),
        Center(child: SageIcon(size: 64, color: theme.colorScheme.onSurface, accent: maroon)),
        const SizedBox(height: 16),
        Center(
          child: Text('Namaskar 🙏', style: theme.textTheme.titleLarge),
        ),
        const SizedBox(height: 8),
        Center(
          child: Text(
            'Prices, news, market mood ya portfolio — kuch bhi poochhiye.\nEnglish, हिंदी ya Hinglish, jaise aap chahein.',
            textAlign: TextAlign.center,
            style: TextStyle(color: theme.colorScheme.onSurfaceVariant, height: 1.5),
          ),
        ),
        const SizedBox(height: 24),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          alignment: WrapAlignment.center,
          children: _suggestions.map((s) {
            return ActionChip(
              label: Text(s, style: const TextStyle(fontSize: 12.5)),
              onPressed: () => _chat.send(s),
              side: BorderSide(color: theme.dividerColor),
            );
          }).toList(),
        ),
      ],
    );
  }

  Widget _messageBubble(BuildContext context, ChatMessage m) {
    final theme = Theme.of(context);
    final maroon = _maroon(context);

    if (m.isUser) {
      return Align(
        alignment: Alignment.centerRight,
        child: Container(
          margin: const EdgeInsets.only(top: 6, bottom: 6, left: 48),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: BoxDecoration(
            color: maroon,
            borderRadius: const BorderRadius.only(
              topLeft: Radius.circular(16),
              topRight: Radius.circular(16),
              bottomLeft: Radius.circular(16),
              bottomRight: Radius.circular(4),
            ),
          ),
          child: Text(m.text, style: const TextStyle(color: Colors.white, height: 1.4)),
        ),
      );
    }

    // Assistant bubble
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(top: 6, bottom: 6, right: 40),
        constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.86),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 28,
                  height: 28,
                  margin: const EdgeInsets.only(top: 2, right: 8),
                  decoration: BoxDecoration(
                    color: maroon.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  alignment: Alignment.center,
                  child: SageIcon(size: 18, color: theme.colorScheme.onSurface, accent: maroon),
                ),
                Flexible(
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                    decoration: BoxDecoration(
                      color: theme.cardColor,
                      borderRadius: const BorderRadius.only(
                        topLeft: Radius.circular(4),
                        topRight: Radius.circular(16),
                        bottomLeft: Radius.circular(16),
                        bottomRight: Radius.circular(16),
                      ),
                      border: Border.all(color: theme.dividerColor),
                    ),
                    child: _assistantContent(context, m),
                  ),
                ),
              ],
            ),
            Padding(
              padding: const EdgeInsets.only(left: 36, top: 2),
              child: InkWell(
                onTap: _showDisclaimer,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(LucideIcons.info, size: 11, color: theme.colorScheme.onSurfaceVariant),
                    const SizedBox(width: 4),
                    Text('Not financial advice',
                        style: TextStyle(fontSize: 10, color: theme.colorScheme.onSurfaceVariant)),
                  ],
                ),
              ),
            ),
            if (m.confirm != null) _confirmCard(context, m),
          ],
        ),
      ),
    );
  }

  Widget _assistantContent(BuildContext context, ChatMessage m) {
    final theme = Theme.of(context);
    final maroon = _maroon(context);

    // Tool activity chip while nothing has streamed yet.
    if (m.streaming && m.text.isEmpty) {
      return Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox(
            width: 14,
            height: 14,
            child: CircularProgressIndicator(strokeWidth: 2, color: maroon),
          ),
          const SizedBox(width: 10),
          Text(_toolLabel(m.tool), style: TextStyle(color: theme.colorScheme.onSurfaceVariant, fontSize: 13)),
        ],
      );
    }

    // Plain text while streaming (markdown may be mid-token); rendered markdown once done.
    if (m.streaming) {
      return Text(m.text, style: TextStyle(color: theme.colorScheme.onSurface, height: 1.5));
    }

    return MarkdownBody(
      data: m.text,
      selectable: true,
      onTapLink: (text, href, title) {
        if (href != null) launchUrl(Uri.parse(href), mode: LaunchMode.externalApplication);
      },
      styleSheet: MarkdownStyleSheet.fromTheme(theme).copyWith(
        p: TextStyle(color: theme.colorScheme.onSurface, height: 1.5, fontSize: 14),
        listBullet: TextStyle(color: theme.colorScheme.onSurface, fontSize: 14),
        strong: TextStyle(color: theme.colorScheme.onSurface, fontWeight: FontWeight.w700),
        a: TextStyle(color: maroon, decoration: TextDecoration.underline),
        code: TextStyle(
          backgroundColor: theme.colorScheme.surfaceContainerHighest,
          fontFamily: 'monospace',
          fontSize: 13,
        ),
      ),
    );
  }

  Widget _confirmCard(BuildContext context, ChatMessage m) {
    final theme = Theme.of(context);
    final maroon = _maroon(context);
    final c = m.confirm!;
    return Container(
      margin: const EdgeInsets.only(left: 36, top: 8),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: maroon.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: maroon.withValues(alpha: 0.35)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Confirm portfolio entry', style: TextStyle(fontWeight: FontWeight.w700, color: theme.colorScheme.onSurface)),
          const SizedBox(height: 6),
          Text(
            '${c.quantity} × ${c.symbol} @ ₹${c.avgPrice.toStringAsFixed(2)}',
            style: TextStyle(color: theme.colorScheme.onSurface, fontSize: 13),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              ElevatedButton(
                onPressed: m.confirmed ? null : () => _chat.confirmHolding(m),
                style: ElevatedButton.styleFrom(
                  backgroundColor: maroon,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 8),
                ),
                child: const Text('Confirm'),
              ),
              const SizedBox(width: 10),
              OutlinedButton(
                onPressed: m.confirmed ? null : () => _chat.cancelHolding(m),
                child: const Text('Cancel'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _inputBar(BuildContext context) {
    final theme = Theme.of(context);
    final maroon = _maroon(context);
    final recording = _voice.recording;
    final transcribing = _voice.transcribing;

    return SafeArea(
      top: false,
      child: Container(
        padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
        decoration: BoxDecoration(
          color: theme.scaffoldBackgroundColor,
          border: Border(top: BorderSide(color: theme.dividerColor)),
        ),
        child: recording
            ? _recordingBar(context)
            : Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  _circleButton(
                    context,
                    icon: LucideIcons.mic,
                    active: false,
                    onTap: transcribing ? null : _toggleMic,
                    busy: transcribing,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Container(
                      constraints: const BoxConstraints(maxHeight: 120),
                      decoration: BoxDecoration(
                        color: theme.cardColor,
                        borderRadius: BorderRadius.circular(22),
                        border: Border.all(color: theme.dividerColor),
                      ),
                      child: TextField(
                        controller: _input,
                        minLines: 1,
                        maxLines: 5,
                        textInputAction: TextInputAction.send,
                        onSubmitted: (_) => _sendCurrent(),
                        decoration: InputDecoration(
                          hintText: 'Type or speak — English / हिंदी / Hinglish',
                          border: InputBorder.none,
                          enabledBorder: InputBorder.none,
                          focusedBorder: InputBorder.none,
                          contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                          hintStyle: TextStyle(color: theme.colorScheme.onSurfaceVariant, fontSize: 13),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  _circleButton(
                    context,
                    icon: LucideIcons.send,
                    active: true,
                    filled: true,
                    color: maroon,
                    onTap: _chat.isBusy ? null : _sendCurrent,
                  ),
                ],
              ),
      ),
    );
  }

  /// Recording state: a live waveform + a clear Stop button.
  Widget _recordingBar(BuildContext context) {
    final theme = Theme.of(context);
    final maroon = _maroon(context);
    return Row(
      children: [
        IconButton(
          tooltip: 'Cancel',
          onPressed: () => _voice.cancelRecording(),
          icon: Icon(LucideIcons.x, color: theme.colorScheme.onSurfaceVariant),
        ),
        Expanded(
          child: Container(
            height: 46,
            padding: const EdgeInsets.symmetric(horizontal: 14),
            decoration: BoxDecoration(
              color: maroon.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(23),
              border: Border.all(color: maroon.withValues(alpha: 0.25)),
            ),
            child: Center(
              child: VoiceWave(level: _voice.level, color: maroon, height: 30),
            ),
          ),
        ),
        const SizedBox(width: 8),
        // Stop button — clearly labelled, red-toned.
        Material(
          color: maroon,
          borderRadius: BorderRadius.circular(23),
          child: InkWell(
            borderRadius: BorderRadius.circular(23),
            onTap: _toggleMic,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: const [
                  Icon(LucideIcons.square, size: 16, color: Colors.white),
                  SizedBox(width: 7),
                  Text('Stop', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _circleButton(
    BuildContext context, {
    required IconData icon,
    required bool active,
    bool filled = false,
    bool busy = false,
    Color? color,
    VoidCallback? onTap,
  }) {
    final theme = Theme.of(context);
    final maroon = color ?? _maroon(context);
    final bg = filled
        ? maroon
        : (active ? maroon.withValues(alpha: 0.15) : theme.cardColor);
    final fg = filled ? Colors.white : (active ? maroon : theme.colorScheme.onSurfaceVariant);
    return Material(
      color: bg,
      shape: CircleBorder(side: filled ? BorderSide.none : BorderSide(color: theme.dividerColor)),
      child: InkWell(
        customBorder: const CircleBorder(),
        onTap: onTap,
        child: SizedBox(
          width: 44,
          height: 44,
          child: busy
              ? Padding(
                  padding: const EdgeInsets.all(12),
                  child: CircularProgressIndicator(strokeWidth: 2, color: maroon),
                )
              : Icon(icon, size: 20, color: onTap == null ? theme.disabledColor : fg),
        ),
      ),
    );
  }

  String _toolLabel(String? tool) {
    switch (tool) {
      case 'get_market_overview':
        return 'Checking the market…';
      case 'get_top_movers':
        return 'Finding top movers…';
      case 'get_stock_price':
        return 'Fetching the price…';
      case 'get_stock_quote':
        return 'Fetching the price…';
      case 'get_announcements':
        return 'Reading announcements…';
      case 'get_news':
        return 'Reading the latest news…';
      case 'elaborate_news':
        return 'Reading the full story…';
      case 'get_sentiment':
        return 'Gauging the mood…';
      case 'get_52_week_range':
        return 'Checking the range…';
      case 'get_price_on_date':
        return 'Looking up that date…';
      case 'get_portfolio':
        return 'Opening your portfolio…';
      case 'record_holding':
        return 'Preparing the entry…';
      default:
        return 'Working…';
    }
  }
}
