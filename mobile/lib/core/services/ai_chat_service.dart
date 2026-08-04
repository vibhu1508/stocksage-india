import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:web_socket_channel/status.dart' as ws_status;

import '../../config/api_config.dart';
import 'api_service.dart';

/// A pending portfolio add awaiting the user's confirmation.
class HoldingConfirm {
  final String symbol;
  final int quantity;
  final double avgPrice;

  const HoldingConfirm({
    required this.symbol,
    required this.quantity,
    required this.avgPrice,
  });

  factory HoldingConfirm.fromJson(Map<String, dynamic> j) => HoldingConfirm(
        symbol: (j['symbol'] ?? '').toString(),
        quantity: (j['quantity'] is num) ? (j['quantity'] as num).toInt() : 0,
        avgPrice: (j['avg_price'] is num) ? (j['avg_price'] as num).toDouble() : 0.0,
      );

  Map<String, dynamic> toJson() =>
      {'symbol': symbol, 'quantity': quantity, 'avg_price': avgPrice};
}

class ChatMessage {
  String text;
  final bool isUser;

  /// True while the assistant reply is still streaming in.
  bool streaming;

  /// Name of the tool currently running (shown as an activity chip).
  String? tool;

  /// Portfolio add awaiting confirmation (renders a confirm card).
  HoldingConfirm? confirm;

  /// Set once the user confirmed/cancelled, so the card buttons disable.
  bool confirmed;

  ChatMessage({
    required this.text,
    required this.isUser,
    this.streaming = false,
    this.tool,
    this.confirm,
    this.confirmed = false,
  });
}

/// Talks to the StockSage AI assistant over `WS /api/chat/ws` and exposes the
/// running message list. The socket is opened lazily and reused for the session.
class AiChatService extends ChangeNotifier {
  final List<ChatMessage> messages = [];

  WebSocketChannel? _channel;
  StreamSubscription? _sub;
  Completer<void>? _connecting;
  HoldingConfirm? _pendingConfirm;

  bool get isBusy {
    final last = messages.isNotEmpty ? messages.last : null;
    return last != null && !last.isUser && last.streaming;
  }

  Future<void> send(String text) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty || isBusy) return;

    messages.add(ChatMessage(text: trimmed, isUser: true));
    messages.add(ChatMessage(text: '', isUser: false, streaming: true));
    notifyListeners();

    await _sendPayload({'message': trimmed});
  }

  Future<void> confirmHolding(ChatMessage msg) async {
    if (msg.confirm == null || msg.confirmed) return;
    msg.confirmed = true;
    messages.add(ChatMessage(text: '', isUser: false, streaming: true));
    notifyListeners();
    await _sendPayload({'action': 'confirm_holding', 'holding': msg.confirm!.toJson()});
  }

  Future<void> cancelHolding(ChatMessage msg) async {
    if (msg.confirm == null || msg.confirmed) return;
    msg.confirmed = true;
    messages.add(ChatMessage(text: '', isUser: false, streaming: true));
    notifyListeners();
    await _sendPayload({'action': 'cancel_holding'});
  }

  void reset() {
    messages.clear();
    notifyListeners();
  }

  // ── internals ──

  Future<void> _sendPayload(Map<String, dynamic> payload) async {
    try {
      final ch = await _ensureSocket();
      ch.sink.add(jsonEncode(payload));
    } catch (_) {
      _finishWithError('Could not connect to the assistant. Please try again.');
    }
  }

  Future<WebSocketChannel> _ensureSocket() async {
    final existing = _channel;
    if (existing != null && _sub != null) return existing;
    if (_connecting != null) {
      await _connecting!.future;
      return _channel!;
    }

    final completer = Completer<void>();
    _connecting = completer;
    try {
      final token = await ApiService.getToken();
      final channel = WebSocketChannel.connect(Uri.parse(ApiConfig.chatWs(token)));
      await channel.ready;
      _channel = channel;
      _sub = channel.stream.listen(
        _onData,
        onError: (_) => _onClosed(),
        onDone: _onClosed,
      );
      completer.complete();
      return channel;
    } catch (e) {
      completer.completeError(e);
      rethrow;
    } finally {
      _connecting = null;
    }
  }

  void _onData(dynamic raw) {
    Map<String, dynamic> ev;
    try {
      ev = jsonDecode(raw as String) as Map<String, dynamic>;
    } catch (_) {
      return;
    }

    switch (ev['type']) {
      case 'token':
        _updateLastAssistant((m) {
          m.text += (ev['text'] ?? '').toString();
          m.tool = null;
        });
        break;
      case 'tool':
        _updateLastAssistant((m) => m.tool = ev['name']?.toString());
        break;
      case 'confirm_request':
        final h = ev['holding'];
        _pendingConfirm = (h is Map<String, dynamic>) ? HoldingConfirm.fromJson(h) : null;
        break;
      case 'done':
        final confirm = _pendingConfirm;
        _pendingConfirm = null;
        _updateLastAssistant((m) {
          m.streaming = false;
          m.tool = null;
          m.confirm = confirm ?? m.confirm;
        });
        break;
      case 'error':
        _finishWithError((ev['detail'] ?? 'Something went wrong.').toString());
        break;
    }
  }

  void _onClosed() {
    _sub?.cancel();
    _sub = null;
    _channel = null;
    if (isBusy) _finishWithError('Connection closed. Please try again.');
  }

  void _finishWithError(String message) {
    _updateLastAssistant((m) {
      if (m.text.isEmpty) m.text = message;
      m.streaming = false;
      m.tool = null;
    });
  }

  void _updateLastAssistant(void Function(ChatMessage) fn) {
    for (var i = messages.length - 1; i >= 0; i--) {
      if (!messages[i].isUser) {
        fn(messages[i]);
        notifyListeners();
        return;
      }
    }
  }

  @override
  void dispose() {
    _sub?.cancel();
    _channel?.sink.close(ws_status.normalClosure);
    super.dispose();
  }
}
