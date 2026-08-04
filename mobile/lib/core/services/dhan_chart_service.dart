import '../../config/api_config.dart';
import 'api_service.dart';

enum ChartTimeframe { one, five, fifteen, sixty, daily }

extension ChartTimeframeWire on ChartTimeframe {
  String get wire {
    switch (this) {
      case ChartTimeframe.one:
        return '1';
      case ChartTimeframe.five:
        return '5';
      case ChartTimeframe.fifteen:
        return '15';
      case ChartTimeframe.sixty:
        return '60';
      case ChartTimeframe.daily:
        return 'D';
    }
  }

  String get label {
    switch (this) {
      case ChartTimeframe.one:
        return '1m';
      case ChartTimeframe.five:
        return '5m';
      case ChartTimeframe.fifteen:
        return '15m';
      case ChartTimeframe.sixty:
        return '1h';
      case ChartTimeframe.daily:
        return '1D';
    }
  }
}

class DhanChartIdentity {
  final String symbol;
  final String securityId;
  final String exchangeSegment;
  final String instrument;

  DhanChartIdentity({
    required this.symbol,
    required this.securityId,
    required this.exchangeSegment,
    required this.instrument,
  });

  factory DhanChartIdentity.fromJson(Map<String, dynamic> json) {
    return DhanChartIdentity(
      symbol: (json['symbol'] ?? '').toString(),
      securityId: (json['securityId'] ?? '').toString(),
      exchangeSegment: (json['exchangeSegment'] ?? '').toString(),
      instrument: (json['instrument'] ?? '').toString(),
    );
  }
}

class DhanChartCandle {
  final int time;
  final double open;
  final double high;
  final double low;
  final double close;

  DhanChartCandle({
    required this.time,
    required this.open,
    required this.high,
    required this.low,
    required this.close,
  });

  factory DhanChartCandle.fromJson(Map<String, dynamic> json) {
    return DhanChartCandle(
      time: (json['time'] as num?)?.toInt() ?? 0,
      open: (json['open'] as num?)?.toDouble() ?? 0,
      high: (json['high'] as num?)?.toDouble() ?? 0,
      low: (json['low'] as num?)?.toDouble() ?? 0,
      close: (json['close'] as num?)?.toDouble() ?? 0,
    );
  }
}

class DhanChartBootstrapResponse {
  final String symbol;
  final String timeframe;
  final String resolvedTimeframe;
  final DhanChartIdentity identity;
  final String source;
  final List<DhanChartCandle> candles;

  DhanChartBootstrapResponse({
    required this.symbol,
    required this.timeframe,
    required this.resolvedTimeframe,
    required this.identity,
    required this.source,
    required this.candles,
  });

  factory DhanChartBootstrapResponse.fromJson(Map<String, dynamic> json) {
    final rawCandles = (json['candles'] as List? ?? [])
        .whereType<Map>()
        .map((e) => DhanChartCandle.fromJson(Map<String, dynamic>.from(e)))
        .toList()
      ..sort((a, b) => a.time.compareTo(b.time));

    return DhanChartBootstrapResponse(
      symbol: (json['symbol'] ?? '').toString(),
      timeframe: (json['timeframe'] ?? '').toString(),
      resolvedTimeframe: (json['resolvedTimeframe'] ?? json['timeframe'] ?? '').toString(),
      identity: DhanChartIdentity.fromJson(Map<String, dynamic>.from(json['identity'] ?? {})),
      source: (json['source'] ?? '').toString(),
      candles: rawCandles,
    );
  }
}

class DhanChartTickResponse {
  final DhanChartIdentity identity;
  final String event;
  final String symbol;
  final String timeframe;
  final int timestamp;
  final double price;
  final String source;

  DhanChartTickResponse({
    required this.identity,
    required this.event,
    required this.symbol,
    required this.timeframe,
    required this.timestamp,
    required this.price,
    required this.source,
  });

  factory DhanChartTickResponse.fromJson(Map<String, dynamic> json) {
    return DhanChartTickResponse(
      identity: DhanChartIdentity.fromJson(Map<String, dynamic>.from(json['identity'] ?? {})),
      event: (json['event'] ?? '').toString(),
      symbol: (json['symbol'] ?? '').toString(),
      timeframe: (json['timeframe'] ?? '').toString(),
      timestamp: (json['timestamp'] as num?)?.toInt() ?? 0,
      price: (json['price'] as num?)?.toDouble() ?? 0,
      source: (json['source'] ?? '').toString(),
    );
  }
}

class DhanDepthLevel {
  final int orders;
  final int quantity;
  final double price;

  DhanDepthLevel({
    required this.orders,
    required this.quantity,
    required this.price,
  });

  factory DhanDepthLevel.fromJson(Map<String, dynamic> json) {
    return DhanDepthLevel(
      orders: (json['orders'] as num?)?.toInt() ?? 0,
      quantity: (json['quantity'] as num?)?.toInt() ?? 0,
      price: (json['price'] as num?)?.toDouble() ?? 0,
    );
  }
}

class DhanMarketDepthResponse {
  final String symbol;
  final int limit;
  final String mode;
  final List<DhanDepthLevel> buy;
  final List<DhanDepthLevel> sell;

  DhanMarketDepthResponse({
    required this.symbol,
    required this.limit,
    required this.mode,
    required this.buy,
    required this.sell,
  });

  factory DhanMarketDepthResponse.fromJson(Map<String, dynamic> json) {
    final buy = (json['buy'] as List? ?? const [])
        .whereType<Map>()
        .map((e) => DhanDepthLevel.fromJson(Map<String, dynamic>.from(e)))
        .toList();
    final sell = (json['sell'] as List? ?? const [])
        .whereType<Map>()
        .map((e) => DhanDepthLevel.fromJson(Map<String, dynamic>.from(e)))
        .toList();

    return DhanMarketDepthResponse(
      symbol: (json['symbol'] ?? '').toString(),
      limit: (json['limit'] as num?)?.toInt() ?? 20,
      mode: (json['mode'] ?? '').toString(),
      buy: buy,
      sell: sell,
    );
  }
}

class MarketSessionStatus {
  final String marketStatus;
  final bool isOpen;
  final bool isTradingDay;
  final String reason;
  final String timestamp;

  MarketSessionStatus({
    required this.marketStatus,
    required this.isOpen,
    required this.isTradingDay,
    required this.reason,
    required this.timestamp,
  });

  factory MarketSessionStatus.fromJson(Map<String, dynamic> json) {
    return MarketSessionStatus(
      marketStatus: (json['market_status'] ?? 'Unknown').toString(),
      isOpen: json['is_open'] == true,
      isTradingDay: json['is_trading_day'] == true,
      reason: (json['reason'] ?? '').toString(),
      timestamp: (json['timestamp'] ?? '').toString(),
    );
  }
}

class DhanChartService {
  static Uri chartWebSocketUri({
    required String symbol,
    required ChartTimeframe timeframe,
    String? securityId,
    String? exchangeSegment,
    String? instrument,
  }) {
    final base = Uri.parse(ApiConfig.baseUrl);
    final wsScheme = base.scheme == 'https' ? 'wss' : 'ws';

    final params = <String, String>{
      'symbol': symbol.trim().toUpperCase(),
      'timeframe': timeframe.wire,
    };

    final normalizedSecurityId = (securityId ?? '').trim();
    if (RegExp(r'^\d+$').hasMatch(normalizedSecurityId)) {
      params['securityId'] = normalizedSecurityId;
    }
    if ((exchangeSegment ?? '').trim().isNotEmpty) {
      params['exchangeSegment'] = exchangeSegment!.trim();
    }
    if ((instrument ?? '').trim().isNotEmpty) {
      params['instrument'] = instrument!.trim();
    }

    return Uri(
      scheme: wsScheme,
      host: base.host,
      port: base.hasPort ? base.port : null,
      path: '/api/market/dhan/chart/ws',
      queryParameters: params,
    );
  }

  static Future<DhanChartBootstrapResponse> getBootstrap({
    required String symbol,
    required ChartTimeframe timeframe,
    String? securityId,
    String? exchangeSegment,
    String? instrument,
  }) async {
    final query = <String, String>{
      'symbol': symbol.trim().toUpperCase(),
      'timeframe': timeframe.wire,
    };

    final normalizedSecurityId = (securityId ?? '').trim();
    if (RegExp(r'^\d+$').hasMatch(normalizedSecurityId)) {
      query['securityId'] = normalizedSecurityId;
    }
    if ((exchangeSegment ?? '').trim().isNotEmpty) {
      query['exchangeSegment'] = exchangeSegment!.trim();
    }
    if ((instrument ?? '').trim().isNotEmpty) {
      query['instrument'] = instrument!.trim();
    }

    final response = await ApiService.get(
      ApiConfig.dhanChartBootstrap,
      queryParams: query,
    );

    final data = ApiService.decodeResponse(response);
    return DhanChartBootstrapResponse.fromJson(data);
  }

  /// Static historical candles for an explicit [fromDate]..[toDate] window
  /// (YYYY-MM-DD). Unlike bootstrap this never opens a live stream, so it lets
  /// the user scroll back and view old data for any range the backend allows.
  static Future<DhanChartBootstrapResponse> getHistory({
    required String symbol,
    required ChartTimeframe timeframe,
    required String fromDate,
    required String toDate,
    String? securityId,
    String? exchangeSegment,
    String? instrument,
  }) async {
    final query = <String, String>{
      'symbol': symbol.trim().toUpperCase(),
      'timeframe': timeframe.wire,
      'fromDate': fromDate,
      'toDate': toDate,
    };

    final normalizedSecurityId = (securityId ?? '').trim();
    if (RegExp(r'^\d+$').hasMatch(normalizedSecurityId)) {
      query['securityId'] = normalizedSecurityId;
    }
    if ((exchangeSegment ?? '').trim().isNotEmpty) {
      query['exchangeSegment'] = exchangeSegment!.trim();
    }
    if ((instrument ?? '').trim().isNotEmpty) {
      query['instrument'] = instrument!.trim();
    }

    final response = await ApiService.get(
      ApiConfig.dhanChartHistory,
      queryParams: query,
    );

    final data = ApiService.decodeResponse(response);
    return DhanChartBootstrapResponse.fromJson(data);
  }

  static Future<DhanChartTickResponse> getLatestTick({
    required String symbol,
    required ChartTimeframe timeframe,
    String? securityId,
    String? exchangeSegment,
    String? instrument,
  }) async {
    final query = <String, String>{
      'symbol': symbol.trim().toUpperCase(),
      'timeframe': timeframe.wire,
    };

    final normalizedSecurityId = (securityId ?? '').trim();
    if (RegExp(r'^\d+$').hasMatch(normalizedSecurityId)) {
      query['securityId'] = normalizedSecurityId;
    }
    if ((exchangeSegment ?? '').trim().isNotEmpty) {
      query['exchangeSegment'] = exchangeSegment!.trim();
    }
    if ((instrument ?? '').trim().isNotEmpty) {
      query['instrument'] = instrument!.trim();
    }

    final response = await ApiService.get(
      ApiConfig.dhanChartLatest,
      queryParams: query,
    );

    final data = ApiService.decodeResponse(response);
    return DhanChartTickResponse.fromJson(data);
  }

  static Future<MarketSessionStatus> getSessionStatus() async {
    try {
      final response = await ApiService.get(ApiConfig.marketSessionStatus);
      final data = ApiService.decodeResponse(response);
      return MarketSessionStatus.fromJson(data);
    } catch (_) {
      final status = _localMarketStatus();
      return MarketSessionStatus(
        marketStatus: status,
        isOpen: status == 'Open',
        isTradingDay: status != 'Closed',
        reason: 'local_fallback',
        timestamp: DateTime.now().toIso8601String(),
      );
    }
  }

  static Future<DhanMarketDepthResponse> getMarketDepth({
    required String symbol,
    required ChartTimeframe timeframe,
    int limit = 20,
    String? securityId,
    String? exchangeSegment,
    String? instrument,
  }) async {
    final query = <String, String>{
      'symbol': symbol.trim().toUpperCase(),
      'timeframe': timeframe.wire,
      'limit': limit.toString(),
    };

    final normalizedSecurityId = (securityId ?? '').trim();
    if (RegExp(r'^\d+$').hasMatch(normalizedSecurityId)) {
      query['securityId'] = normalizedSecurityId;
    }
    if ((exchangeSegment ?? '').trim().isNotEmpty) {
      query['exchangeSegment'] = exchangeSegment!.trim();
    }
    if ((instrument ?? '').trim().isNotEmpty) {
      query['instrument'] = instrument!.trim();
    }

    final response = await ApiService.get(
      ApiConfig.dhanQuoteDepth,
      queryParams: query,
    );

    final data = ApiService.decodeResponse(response);
    return DhanMarketDepthResponse.fromJson(data);
  }

  static String _localMarketStatus() {
    final now = DateTime.now().toUtc().add(const Duration(hours: 5, minutes: 30));
    final weekday = now.weekday;
    if (weekday >= 6) return 'Closed';

    final minutes = now.hour * 60 + now.minute;
    if (minutes < 540) return 'Pre-Market';
    if (minutes < 555) return 'Pre-Open';
    if (minutes <= 930) return 'Open';
    return 'Closed';
  }
}
