import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

import '../../config/api_config.dart';

/// Voice I/O for the assistant.
///
/// STT: records mic audio and uploads it to the backend, which transcribes with
/// Whisper (English / Hindi / Hinglish). TTS: reads replies aloud with the
/// device's text-to-speech engine, picking a Hindi or English voice by script.
class VoiceService extends ChangeNotifier {
  final AudioRecorder _recorder = AudioRecorder();
  final FlutterTts _tts = FlutterTts();

  bool recording = false;
  bool transcribing = false;
  bool speaking = false;
  bool _ttsReady = false;

  /// Live mic loudness, normalised 0..1, for the recording animation.
  final ValueNotifier<double> level = ValueNotifier<double>(0);
  StreamSubscription<Amplitude>? _ampSub;

  VoiceService() {
    _tts.setStartHandler(() {
      speaking = true;
      notifyListeners();
    });
    _tts.setCompletionHandler(() {
      speaking = false;
      notifyListeners();
    });
    _tts.setCancelHandler(() {
      speaking = false;
      notifyListeners();
    });
    _tts.setErrorHandler((_) {
      speaking = false;
      notifyListeners();
    });
  }

  // ── Speech to text ──

  /// Returns true if recording actually started.
  Future<bool> startRecording({void Function(String)? onError}) async {
    if (recording) return false;
    await stopSpeaking(); // barge-in
    try {
      if (!await _recorder.hasPermission()) {
        onError?.call('Microphone permission is needed for voice input.');
        return false;
      }
      final dir = await getTemporaryDirectory();
      final path = '${dir.path}/sage_clip_${DateTime.now().millisecondsSinceEpoch}.m4a';
      await _recorder.start(
        const RecordConfig(encoder: AudioEncoder.aacLc, sampleRate: 16000, numChannels: 1),
        path: path,
      );
      recording = true;
      notifyListeners();
      // Drive the waveform from live mic loudness (dBFS → 0..1).
      _ampSub?.cancel();
      _ampSub = _recorder
          .onAmplitudeChanged(const Duration(milliseconds: 90))
          .listen((amp) {
        final db = amp.current; // ~ -60 (quiet) .. 0 (loud)
        level.value = ((db + 50) / 50).clamp(0.0, 1.0);
      });
      return true;
    } catch (e) {
      recording = false;
      notifyListeners();
      onError?.call('Could not start recording.');
      return false;
    }
  }

  /// Stop recording, upload, and return the transcript ('' on failure).
  Future<String> stopRecording() async {
    if (!recording) return '';
    String? path;
    try {
      path = await _recorder.stop();
    } catch (_) {
      path = null;
    }
    await _ampSub?.cancel();
    _ampSub = null;
    level.value = 0;
    recording = false;
    notifyListeners();
    if (path == null) return '';

    transcribing = true;
    notifyListeners();
    try {
      return await _upload(File(path));
    } catch (_) {
      return '';
    } finally {
      transcribing = false;
      notifyListeners();
      try {
        await File(path).delete();
      } catch (_) {}
    }
  }

  Future<void> cancelRecording() async {
    if (!recording) return;
    try {
      final path = await _recorder.stop();
      if (path != null) await File(path).delete();
    } catch (_) {}
    await _ampSub?.cancel();
    _ampSub = null;
    level.value = 0;
    recording = false;
    notifyListeners();
  }

  Future<String> _upload(File file) async {
    final req = http.MultipartRequest('POST', Uri.parse(ApiConfig.chatTranscribe));
    req.files.add(await http.MultipartFile.fromPath('audio', file.path, filename: 'clip.m4a'));
    final streamed = await req.send().timeout(const Duration(seconds: 60));
    if (streamed.statusCode != 200) return '';
    final body = await streamed.stream.bytesToString();
    // Backend returns {"text": ..., "language": ...}
    final match = RegExp(r'"text"\s*:\s*"((?:[^"\\]|\\.)*)"').firstMatch(body);
    if (match == null) return '';
    return _unescapeJson(match.group(1) ?? '').trim();
  }

  String _unescapeJson(String s) => s
      .replaceAll(r'\"', '"')
      .replaceAll(r'\n', '\n')
      .replaceAll(r'\/', '/')
      .replaceAll(r'\\', '\\');

  // ── Text to speech ──

  Future<void> speak(String text) async {
    final t = text.trim();
    if (t.isEmpty) return;
    await stopSpeaking();
    final isDevanagari = RegExp(r'[ऀ-ॿ]').hasMatch(t);
    try {
      if (!_ttsReady) {
        await _tts.awaitSpeakCompletion(true);
        _ttsReady = true;
      }
      await _tts.setLanguage(isDevanagari ? 'hi-IN' : 'en-IN');
      await _tts.setSpeechRate(0.5);
      await _tts.speak(t);
    } catch (_) {
      speaking = false;
      notifyListeners();
    }
  }

  Future<void> stopSpeaking() async {
    try {
      await _tts.stop();
    } catch (_) {}
    speaking = false;
    notifyListeners();
  }

  @override
  void dispose() {
    _ampSub?.cancel();
    level.dispose();
    _recorder.dispose();
    _tts.stop();
    super.dispose();
  }
}
