import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import '../../config/api_config.dart';

class MarketData {
  final String marketStatus;
  final IndexData? sensex;
  final IndexData? nifty;
  final String timestamp;

  MarketData({
    required this.marketStatus,
    this.sensex,
    this.nifty,
    required this.timestamp,
  });

  factory MarketData.fromJson(Map<String, dynamic> json) {
    return MarketData(
      marketStatus: json['market_status'] ?? 'Unknown',
      sensex: json['sensex'] != null
          ? IndexData.fromJson(json['sensex'])
          : null,
      nifty: json['nifty'] != null ? IndexData.fromJson(json['nifty']) : null,
      timestamp: json['timestamp'] ?? '',
    );
  }
}

class IndexData {
  final String name;
  final String value;
  final String change;
  final String pctChange;
  final String high;
  final String low;
  final String open;
  final String prevClose;

  IndexData({
    required this.name,
    required this.value,
    required this.change,
    required this.pctChange,
    required this.high,
    required this.low,
    required this.open,
    required this.prevClose,
  });

  factory IndexData.fromJson(Map<String, dynamic> json) {
    return IndexData(
      name: json['name'] ?? '',
      value: json['value']?.toString() ?? '0',
      change: json['change']?.toString() ?? '0',
      pctChange: json['pct_change']?.toString() ?? '0',
      high: json['high']?.toString() ?? '0',
      low: json['low']?.toString() ?? '0',
      open: json['open']?.toString() ?? '0',
      prevClose: json['prev_close']?.toString() ?? '0',
    );
  }

  double get valueNum => double.tryParse(value.replaceAll(',', '')) ?? 0;
  double get changeNum => double.tryParse(change.replaceAll(',', '')) ?? 0;
  double get pctChangeNum =>
      double.tryParse(pctChange.replaceAll(',', '')) ?? 0;
  bool get isPositive => changeNum >= 0;

  String get formattedValue {
    final num = valueNum;
    if (num == 0) return value;
    // Format with commas (Indian style)
    final parts = num.toStringAsFixed(2).split('.');
    final intPart = parts[0];
    final decPart = parts[1];

    // Indian comma format: 1,23,456
    if (intPart.length <= 3) return '$intPart.$decPart';
    String result = intPart.substring(intPart.length - 3);
    String remaining = intPart.substring(0, intPart.length - 3);
    while (remaining.length > 2) {
      result = '${remaining.substring(remaining.length - 2)},$result';
      remaining = remaining.substring(0, remaining.length - 2);
    }
    if (remaining.isNotEmpty) result = '$remaining,$result';
    return '$result.$decPart';
  }
}

class MarketService {
  static Future<MarketData> getLiveData() async {
    try {
      final response = await http
          .get(Uri.parse(ApiConfig.marketLive))
          .timeout(const Duration(seconds: 15));

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        return MarketData.fromJson(data);
      }
      throw Exception('Failed to fetch market data');
    } catch (e) {
      // Return fallback with market status only
      return MarketData(
        marketStatus: _getLocalMarketStatus(),
        timestamp: DateTime.now().toIso8601String(),
      );
    }
  }

  static String _getLocalMarketStatus() {
    final now = DateTime.now().toUtc().add(
      const Duration(hours: 5, minutes: 30),
    );
    final weekday = now.weekday;
    if (weekday >= 6) return 'Closed';

    final minutes = now.hour * 60 + now.minute;
    if (minutes < 540) return 'Pre-Market';
    if (minutes < 555) return 'Pre-Open';
    if (minutes <= 930) return 'Open';
    return 'Closed';
  }

  /// Fetch top 10 gainers from NSE
  static Future<List<Map<String, dynamic>>> getTopGainers() async {
    try {
      final response = await http
          .get(Uri.parse(ApiConfig.topStocks))
          .timeout(const Duration(seconds: 15));

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        final gainers = data['gainers'] as List? ?? [];
        return gainers.cast<Map<String, dynamic>>();
      }
      return [];
    } catch (_) {
      return [];
    }
  }
}
