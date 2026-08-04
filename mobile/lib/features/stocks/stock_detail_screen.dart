import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:intl/intl.dart' hide TextDirection;
import 'package:url_launcher/url_launcher.dart';

import '../../config/theme.dart';
import '../../core/models/announcement.dart';
import '../../core/services/announcement_service.dart';
import '../../core/services/dhan_chart_service.dart';
import '../portfolio/portfolio_service.dart';
import '../strategy_builder/strategy_service.dart';

class StockDetailScreen extends StatefulWidget {
  final String symbol;

  const StockDetailScreen({super.key, required this.symbol});

  @override
  State<StockDetailScreen> createState() => _StockDetailScreenState();
}

class _StockDetailScreenState extends State<StockDetailScreen> with SingleTickerProviderStateMixin {
  final StrategyService _strategyService = StrategyService();
  final PortfolioService _portfolioService = PortfolioService();

  bool _loading = true;
  String _error = '';

  Map<String, dynamic>? _quote;
  List<NSEAnnouncement> _announcements = [];
  bool _announcementsLoading = false;

  Map<String, dynamic>? _performance;
  bool _performanceLoading = false;

  ChartTimeframe _timeframe = ChartTimeframe.five;
  String _dailyRange = 'MAX';
  static const List<String> _dailyRanges = [
    '1D',
    '5D',
    '1M',
    '3M',
    '6M',
    '1Y',
    '2Y',
    '5Y',
    '10Y',
    'MAX',
  ];

  DateTime? _customFrom;
  DateTime? _customTo;
  String _customRangeError = '';

  // Static "view old data" mode: when the user loads a custom historical window
  // we fetch it from the backend and pause live ticks.
  bool _historyMode = false;
  bool _historyLoading = false;
  String _historyNotice = '';

  bool _chartLoading = false;
  String _chartError = '';
  DateTime? _chartUpdatedAt;
  _LiveTransportStatus _liveTransportStatus = _LiveTransportStatus.idle;
  int _candleCount = 0;
  double _liveLastPrice = 0;
  ChartTimeframe _resolvedTimeframe = ChartTimeframe.five;
  bool _marketDepthLoading = false;
  String _marketDepthError = '';
  int _marketDepthLimit = 20;
  String _marketDepthMode = '';
  List<DhanDepthLevel> _marketDepthBuy = [];
  List<DhanDepthLevel> _marketDepthSell = [];

  DhanChartIdentity? _chartIdentity;
  final Map<String, _ChartSnapshot> _chartCache = {};
  List<DhanChartCandle> _rawCandles = [];
  List<DhanChartCandle> _displayCandles = [];
  double _chartZoom = 1.0;
  double _chartPanBars = 0.0;
  int? _hoveredCandleIndex;
  double _gestureStartZoom = 1.0;

  Timer? _tickTimer;
  WebSocket? _tickSocket;
  StreamSubscription<dynamic>? _tickSocketSub;
  int _tickFailureCount = 0;
  DateTime? _lastSessionCheckAt;
  bool? _lastSessionOpen;
  late final AnimationController _livePulseController;
  late final Animation<double> _livePulseAnimation;

  String get _symbol => widget.symbol.trim().toUpperCase();

  @override
  void initState() {
    super.initState();
    _livePulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    )..repeat(reverse: true);
    _livePulseAnimation = Tween<double>(begin: 0.85, end: 1.2).animate(
      CurvedAnimation(parent: _livePulseController, curve: Curves.easeInOut),
    );
    _loadAll();
  }

  @override
  void dispose() {
    _livePulseController.dispose();
    _tickTimer?.cancel();
    _tickSocketSub?.cancel();
    _tickSocket?.close();
    super.dispose();
  }

  Future<void> _loadAll() async {
    setState(() {
      _loading = true;
      _error = '';
    });

    await Future.wait([
      _loadQuote(),
      _loadAnnouncements(),
      _loadYearwise(),
      _reloadChart(),
      _loadMarketDepth(limit: _marketDepthLimit),
    ]);

    if (!mounted) return;
    setState(() => _loading = false);
  }

  Future<void> _loadQuote() async {
    try {
      final res = await _strategyService.getSymbolData(_symbol);
      if (!mounted) return;
      setState(() {
        _quote = _normalizeQuoteResponse(res);
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _error = 'Unable to load stock details right now.');
    }
  }

  Future<void> _loadAnnouncements() async {
    setState(() => _announcementsLoading = true);
    try {
      final list = await AnnouncementService.getNSEAnnouncements(
        _symbol,
        limit: 8,
      );
      if (!mounted) return;
      setState(() {
        _announcements = list;
        _announcementsLoading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _announcements = [];
        _announcementsLoading = false;
      });
    }
  }

  Future<void> _loadYearwise() async {
    setState(() => _performanceLoading = true);
    try {
      final res = await _strategyService.getYearwiseData(_symbol);
      final data = (res['data'] as List?) ?? const [];
      if (!mounted) return;
      setState(() {
        _performance = data.isNotEmpty && data.first is Map
            ? Map<String, dynamic>.from(data.first)
            : null;
        _performanceLoading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _performance = null;
        _performanceLoading = false;
      });
    }
  }

  Future<void> _loadMarketDepth({required int limit}) async {
    setState(() {
      _marketDepthLoading = true;
      _marketDepthError = '';
      _marketDepthLimit = limit;
    });

    try {
      final res = await DhanChartService.getMarketDepth(
        symbol: _symbol,
        timeframe: _timeframe,
        limit: limit,
        securityId: _chartIdentity?.securityId,
        exchangeSegment: _chartIdentity?.exchangeSegment,
        instrument: _chartIdentity?.instrument,
      );

      if (!mounted) return;
      setState(() {
        _marketDepthBuy = res.buy;
        _marketDepthSell = res.sell;
        _marketDepthMode = res.mode;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _marketDepthError = e.toString().replaceAll('Exception: ', '');
        _marketDepthBuy = [];
        _marketDepthSell = [];
      });
    } finally {
      if (mounted) {
        setState(() => _marketDepthLoading = false);
      }
    }
  }

  void _setMarketDepthLimit(int limit) {
    if (_marketDepthLimit == limit && (_marketDepthBuy.isNotEmpty || _marketDepthSell.isNotEmpty)) {
      return;
    }
    _loadMarketDepth(limit: limit);
  }

  Future<void> _reloadChart() async {
    _tickTimer?.cancel();

    final cacheKey = '${_symbol}_${_timeframe.wire}';
    final cached = _chartCache[cacheKey];
    if (cached != null) {
      _applySnapshot(cached);
      _startTickTimer();
      return;
    }

    setState(() {
      _chartLoading = true;
      _chartError = '';
      _hoveredCandleIndex = null;
      _chartZoom = 1.0;
      _chartPanBars = 0.0;
    });

    try {
      final bootstrap = await DhanChartService.getBootstrap(
        symbol: _symbol,
        timeframe: _timeframe,
      );

      final resolved = _parseTimeframe(bootstrap.resolvedTimeframe);
      final candles = _normalizeCandles(bootstrap.candles);
      final lastPrice = candles.isNotEmpty ? candles.last.close : 0.0;

      final snapshot = _ChartSnapshot(
        identity: bootstrap.identity,
        resolvedTimeframe: resolved,
        candles: candles,
        updatedAt: DateTime.now(),
        lastPrice: lastPrice,
      );

      _chartCache[cacheKey] = snapshot;
      if (!mounted) return;

      _applySnapshot(snapshot);
      _startTickTimer();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _chartError = e.toString().replaceFirst('Exception: ', '');
      });
    } finally {
      if (mounted) setState(() => _chartLoading = false);
    }
  }

  void _applySnapshot(_ChartSnapshot snapshot) {
    _chartIdentity = snapshot.identity;
    _resolvedTimeframe = snapshot.resolvedTimeframe;
    _rawCandles = List<DhanChartCandle>.from(snapshot.candles);
    _liveLastPrice = snapshot.lastPrice;
    _chartUpdatedAt = snapshot.updatedAt;
    _chartError = '';
    _applyRangeFilters();
  }

  Future<void> _onTimeframeChanged(ChartTimeframe tf) async {
    if (_timeframe == tf) return;
    setState(() {
      _timeframe = tf;
      _dailyRange = 'MAX';
      _customFrom = null;
      _customTo = null;
      _customRangeError = '';
      _historyMode = false;
      _historyNotice = '';
    });
    await _reloadChart();
  }

  void _setDailyRange(String range) {
    if (_dailyRange == range) return;
    setState(() {
      _dailyRange = range;
      _customRangeError = '';
    });
    _applyRangeFilters();
  }

  Future<void> _pickDate(bool isFrom) async {
    final now = DateTime.now();
    final initial = isFrom ? (_customFrom ?? now.subtract(const Duration(days: 30))) : (_customTo ?? now);
    final picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(2000),
      lastDate: now,
      builder: (context, child) {
        final isDark = Theme.of(context).brightness == Brightness.dark;
        return Theme(
          data: isDark ? AppTheme.darkTheme : AppTheme.lightTheme,
          child: child ?? const SizedBox.shrink(),
        );
      },
    );
    if (picked == null) return;

    setState(() {
      if (isFrom) {
        _customFrom = picked;
      } else {
        _customTo = picked;
      }
      _customRangeError = '';
    });
  }

  int? _maxRangeDays(ChartTimeframe tf) {
    switch (tf) {
      case ChartTimeframe.one:
        return 30;
      case ChartTimeframe.five:
        return 120;
      case ChartTimeframe.fifteen:
        return 365;
      case ChartTimeframe.sixty:
        return 730;
      case ChartTimeframe.daily:
        return null; // no span limit for daily candles
    }
  }

  String _fmtApiDate(DateTime d) => DateFormat('yyyy-MM-dd').format(d);

  /// Fetch an explicit historical window from the backend and show it statically
  /// (live ticks paused). This is how the user scrolls back to old data.
  Future<void> _loadCustomHistory() async {
    if (_customFrom == null || _customTo == null) {
      setState(() => _customRangeError = 'Pick both From and To dates.');
      return;
    }
    if (_customFrom!.isAfter(_customTo!)) {
      setState(() => _customRangeError = 'From date must be earlier than To date.');
      return;
    }
    final maxDays = _maxRangeDays(_timeframe);
    final spanDays = _customTo!.difference(_customFrom!).inDays;
    if (maxDays != null && spanDays > maxDays) {
      setState(() => _customRangeError =
          '${_timeframe.label} candles are limited to $maxDays days per range. '
          'Pick a shorter window or a larger interval.');
      return;
    }

    // Historical view is static — stop the live stream/poll before loading.
    _tickTimer?.cancel();
    _tickSocketSub?.cancel();
    _tickSocketSub = null;
    _tickSocket?.close();
    _tickSocket = null;

    setState(() {
      _historyLoading = true;
      _chartLoading = true;
      _chartError = '';
      _customRangeError = '';
      _liveTransportStatus = _LiveTransportStatus.idle;
    });

    try {
      final res = await DhanChartService.getHistory(
        symbol: _symbol,
        timeframe: _timeframe,
        fromDate: _fmtApiDate(_customFrom!),
        toDate: _fmtApiDate(_customTo!),
        securityId: _chartIdentity?.securityId,
        exchangeSegment: _chartIdentity?.exchangeSegment,
        instrument: _chartIdentity?.instrument,
      );
      final candles = _normalizeCandles(res.candles);
      if (!mounted) return;
      if (candles.isEmpty) {
        setState(() {
          _historyLoading = false;
          _chartLoading = false;
          _customRangeError =
              'No candles available for that range. Try a wider window or a different interval.';
        });
        return;
      }
      setState(() {
        _chartIdentity = res.identity;
        _resolvedTimeframe = _parseTimeframe(res.resolvedTimeframe);
        _rawCandles = candles;
        _displayCandles = candles;
        _candleCount = candles.length;
        _historyMode = true;
        _historyNotice =
            'Historical · ${_timeframe.label} · ${_fmtApiDate(_customFrom!)} → ${_fmtApiDate(_customTo!)}';
        _liveLastPrice = candles.last.close;
        _chartUpdatedAt = DateTime.now();
        _historyLoading = false;
        _chartLoading = false;
        _chartZoom = 1.0;
        _chartPanBars = 0.0;
        _hoveredCandleIndex = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _historyLoading = false;
        _chartLoading = false;
        _customRangeError = e.toString().replaceFirst('Exception: ', '');
      });
    }
  }

  void _resetCustomDateRange() {
    setState(() {
      _customFrom = null;
      _customTo = null;
      _customRangeError = '';
      _historyNotice = '';
    });
    if (_historyMode) {
      _historyMode = false;
      _reloadChart(); // back to the live/last-session view
    } else {
      _applyRangeFilters();
    }
  }

  void _applyRangeFilters() {
    if (_historyMode) return; // static history view manages its own candles
    List<DhanChartCandle> candles = List<DhanChartCandle>.from(_rawCandles);

    if (_resolvedTimeframe == ChartTimeframe.daily && candles.isNotEmpty) {
      final now = DateTime.now();
      DateTime? from;

      switch (_dailyRange) {
        case '1D':
          from = now.subtract(const Duration(days: 1));
          break;
        case '5D':
          from = now.subtract(const Duration(days: 5));
          break;
        case '1M':
          from = DateTime(now.year, now.month - 1, now.day);
          break;
        case '3M':
          from = DateTime(now.year, now.month - 3, now.day);
          break;
        case '6M':
          from = DateTime(now.year, now.month - 6, now.day);
          break;
        case '1Y':
          from = DateTime(now.year - 1, now.month, now.day);
          break;
        case '2Y':
          from = DateTime(now.year - 2, now.month, now.day);
          break;
        case '5Y':
          from = DateTime(now.year - 5, now.month, now.day);
          break;
        case '10Y':
          from = DateTime(now.year - 10, now.month, now.day);
          break;
        case 'MAX':
          from = null;
          break;
      }

      if (from != null) {
        final fromTs = from.millisecondsSinceEpoch ~/ 1000;
        candles = candles.where((c) => c.time >= fromTs).toList();
      }
    }

    setState(() {
      _displayCandles = candles;
      _candleCount = candles.length;
      _hoveredCandleIndex = null;
      if (candles.isNotEmpty) {
        _liveLastPrice = candles.last.close;
      }
    });
  }

  List<DhanChartCandle> _buildRenderCandles(List<DhanChartCandle> source, {int maxPoints = 700}) {
    if (source.length <= maxPoints) {
      return source;
    }

    final bucketSize = source.length / maxPoints;
    final output = <DhanChartCandle>[];
    for (int i = 0; i < maxPoints; i++) {
      final start = (i * bucketSize).floor();
      final end = math.min(source.length, ((i + 1) * bucketSize).ceil());
      if (start >= end) continue;

      final first = source[start];
      final last = source[end - 1];
      double high = first.high;
      double low = first.low;

      for (int j = start + 1; j < end; j++) {
        high = math.max(high, source[j].high);
        low = math.min(low, source[j].low);
      }

      output.add(
        DhanChartCandle(
          time: last.time,
          open: first.open,
          high: high,
          low: low,
          close: last.close,
        ),
      );
    }

    return output;
  }

  List<DhanChartCandle> _visibleCandles(List<DhanChartCandle> source) {
    if (source.isEmpty) return source;

    final maxVisible = (source.length / _chartZoom).round().clamp(30, source.length);
    int end = source.length - _chartPanBars.round();
    end = end.clamp(maxVisible, source.length);
    final start = math.max(0, end - maxVisible);
    return source.sublist(start, end);
  }

  void _updateHoveredCandle(Offset localPosition, double width, List<DhanChartCandle> visible) {
    if (visible.isEmpty || width <= 0) return;

    final index = ((localPosition.dx / width) * visible.length).floor().clamp(0, visible.length - 1);
    if (_hoveredCandleIndex == index) return;
    setState(() => _hoveredCandleIndex = index);
  }

  void _resetChartView() {
    setState(() {
      _chartZoom = 1.0;
      _chartPanBars = 0.0;
      _hoveredCandleIndex = null;
    });
  }

  void _startTickTimer() {
    _tickTimer?.cancel();
    _tickSocketSub?.cancel();
    _tickSocketSub = null;
    _tickSocket?.close();
    _tickSocket = null;
    _tickFailureCount = 0;
    _liveTransportStatus = _LiveTransportStatus.connecting;

    unawaited(_connectTickStream());
  }

  Future<void> _connectTickStream() async {
    final identity = _chartIdentity;
    if (identity == null || _resolvedTimeframe == ChartTimeframe.daily) {
      if (mounted) {
        setState(() => _liveTransportStatus = _LiveTransportStatus.idle);
      }
      return;
    }

    final sessionOpen = await _isSessionOpen();
    if (!sessionOpen) {
      if (mounted) {
        setState(() => _liveTransportStatus = _LiveTransportStatus.closed);
      }
      return;
    }

    try {
      final uri = DhanChartService.chartWebSocketUri(
        symbol: _symbol,
        timeframe: _resolvedTimeframe,
        securityId: identity.securityId,
        exchangeSegment: identity.exchangeSegment,
        instrument: identity.instrument,
      );

      final socket = await WebSocket.connect(uri.toString());
      socket.pingInterval = const Duration(seconds: 20);

      if (!mounted) {
        await socket.close();
        return;
      }

      _tickSocket = socket;
      _tickSocketSub = socket.listen(
        (event) {
          if (!mounted || event is! String) return;

          try {
            final decoded = jsonDecode(event);
            if (decoded is! Map<String, dynamic>) return;

            if (decoded['event'] != 'chart_tick') {
              return;
            }

            final tick = DhanChartTickResponse.fromJson(decoded);
            if (tick.price <= 0 || tick.timestamp <= 0) return;

            final next = _mergeTickIntoCandles(
              raw: _rawCandles,
              timestamp: tick.timestamp,
              price: tick.price,
              timeframe: _resolvedTimeframe,
            );

            setState(() {
              _rawCandles = next;
              _liveLastPrice = tick.price;
              _chartUpdatedAt = DateTime.now();
              _chartError = '';
              _liveTransportStatus = _LiveTransportStatus.ws;
            });

            _cacheCurrentSnapshot();
            _applyRangeFilters();
            _tickFailureCount = 0;
          } catch (_) {
            // Ignore malformed frames and keep stream alive.
          }
        },
        onError: (_) {
          _startPollingFallback();
        },
        onDone: () {
          if (mounted) {
            _startPollingFallback();
          }
        },
        cancelOnError: false,
      );
    } catch (_) {
      _startPollingFallback();
    }
  }

  void _startPollingFallback() {
    _tickSocketSub?.cancel();
    _tickSocketSub = null;
    _tickSocket?.close();
    _tickSocket = null;

    _tickTimer?.cancel();
    _tickTimer = Timer.periodic(const Duration(seconds: 5), (_) async {
      final sessionOpen = await _isSessionOpen();
      if (!sessionOpen) {
        if (mounted) {
          setState(() => _liveTransportStatus = _LiveTransportStatus.closed);
        }
        return;
      }
      await _pollLatestTick();
    });

    if (mounted) {
      setState(() {
        _chartError = 'Live stream delayed, using polling fallback.';
        _liveTransportStatus = _LiveTransportStatus.polling;
      });
    }
  }

  Future<bool> _isSessionOpen() async {
    final now = DateTime.now();
    if (_lastSessionCheckAt != null &&
        now.difference(_lastSessionCheckAt!).inSeconds < 60 &&
        _lastSessionOpen != null) {
      return _lastSessionOpen!;
    }

    try {
      final status = await DhanChartService.getSessionStatus();
      _lastSessionCheckAt = now;
      _lastSessionOpen = status.isOpen;
      return status.isOpen;
    } catch (_) {
      _lastSessionCheckAt = now;
      _lastSessionOpen = false;
      return false;
    }
  }

  Future<void> _pollLatestTick() async {
    final identity = _chartIdentity;
    if (identity == null) return;

    try {
      final tick = await DhanChartService.getLatestTick(
        symbol: _symbol,
        timeframe: _timeframe,
        securityId: identity.securityId,
        exchangeSegment: identity.exchangeSegment,
        instrument: identity.instrument,
      );

      final next = _mergeTickIntoCandles(
        raw: _rawCandles,
        timestamp: tick.timestamp,
        price: tick.price,
        timeframe: _resolvedTimeframe,
      );

      if (!mounted) return;

      setState(() {
        _rawCandles = next;
        _liveLastPrice = tick.price;
        _chartUpdatedAt = DateTime.now();
        _liveTransportStatus = _LiveTransportStatus.polling;
      });
      _cacheCurrentSnapshot();
      _applyRangeFilters();
      _tickFailureCount = 0;
    } catch (_) {
      _tickFailureCount += 1;
      if (_tickFailureCount >= 5 && mounted) {
        setState(() {
          _chartError = 'Live updates paused due to repeated errors.';
          _liveTransportStatus = _LiveTransportStatus.polling;
        });
        _tickTimer?.cancel();
      }
    }
  }

  void _cacheCurrentSnapshot() {
    final cacheKey = '${_symbol}_${_timeframe.wire}';
    final identity = _chartIdentity;
    if (identity == null) return;

    _chartCache[cacheKey] = _ChartSnapshot(
      identity: identity,
      resolvedTimeframe: _resolvedTimeframe,
      candles: List<DhanChartCandle>.from(_rawCandles),
      updatedAt: DateTime.now(),
      lastPrice: _liveLastPrice,
    );
  }

  List<DhanChartCandle> _mergeTickIntoCandles({
    required List<DhanChartCandle> raw,
    required int timestamp,
    required double price,
    required ChartTimeframe timeframe,
  }) {
    final list = List<DhanChartCandle>.from(raw);
    final bucketTs = _bucketTimestamp(timestamp, timeframe);

    if (list.isEmpty) {
      return [
        DhanChartCandle(
          time: bucketTs,
          open: price,
          high: price,
          low: price,
          close: price,
        ),
      ];
    }

    final last = list.last;
    if (last.time == bucketTs) {
      list[list.length - 1] = DhanChartCandle(
        time: last.time,
        open: last.open,
        high: math.max(last.high, price),
        low: math.min(last.low, price),
        close: price,
      );
      return list;
    }

    if (last.time > bucketTs) {
      return list;
    }

    list.add(
      DhanChartCandle(
        time: bucketTs,
        open: last.close,
        high: math.max(last.close, price),
        low: math.min(last.close, price),
        close: price,
      ),
    );
    return list;
  }

  int _bucketTimestamp(int timestamp, ChartTimeframe timeframe) {
    if (timeframe == ChartTimeframe.daily) {
      final dt = DateTime.fromMillisecondsSinceEpoch(timestamp * 1000, isUtc: true)
          .add(const Duration(hours: 5, minutes: 30));
      final istMidnight = DateTime.utc(dt.year, dt.month, dt.day)
          .subtract(const Duration(hours: 5, minutes: 30));
      return istMidnight.millisecondsSinceEpoch ~/ 1000;
    }

    final minutes = switch (timeframe) {
      ChartTimeframe.one => 1,
      ChartTimeframe.five => 5,
      ChartTimeframe.fifteen => 15,
      ChartTimeframe.sixty => 60,
      ChartTimeframe.daily => 1440,
    };

    final bucket = (timestamp ~/ (minutes * 60)) * (minutes * 60);
    return bucket;
  }

  List<DhanChartCandle> _normalizeCandles(List<DhanChartCandle> input) {
    final map = <int, DhanChartCandle>{};
    for (final candle in input) {
      map[candle.time] = candle;
    }
    final list = map.values.toList()..sort((a, b) => a.time.compareTo(b.time));
    return list;
  }

  ChartTimeframe _parseTimeframe(String raw) {
    switch (raw.toUpperCase()) {
      case '1':
        return ChartTimeframe.one;
      case '5':
        return ChartTimeframe.five;
      case '15':
        return ChartTimeframe.fifteen;
      case '60':
        return ChartTimeframe.sixty;
      case 'D':
        return ChartTimeframe.daily;
      default:
        return _timeframe;
    }
  }

  Map<String, dynamic>? _normalizeQuoteResponse(Map<String, dynamic> res) {
    if (res.isEmpty) return null;

    final first = (res['equityResponse'] is List && (res['equityResponse'] as List).isNotEmpty)
        ? (res['equityResponse'] as List).first
        : null;

    if (first is Map) {
      final firstMap = Map<String, dynamic>.from(first);
      final meta = Map<String, dynamic>.from(firstMap['metaData'] ?? const {});
      final sec = Map<String, dynamic>.from(firstMap['secInfo'] ?? const {});
      final trade = Map<String, dynamic>.from(firstMap['tradeInfo'] ?? const {});
      final price = Map<String, dynamic>.from(firstMap['priceInfo'] ?? const {});
      final orderBook = Map<String, dynamic>.from(firstMap['orderBook'] ?? const {});

      return {
        'info': {
          'companyName': (meta['companyName'] ?? sec['issueDesc'] ?? _symbol).toString(),
        },
        'metadata': {
          ...meta,
          'industry': sec['basicIndustry'] ?? sec['industryInfo'],
          'lastUpdateTime': firstMap['lastUpdateTime'],
        },
        'securityInfo': {
          ...sec,
          'faceValue': trade['faceValue'],
        },
        'tradeInfo': trade,
        'priceInfo': {
          ...price,
          'previousClose': meta['previousClose'] ?? price['previousClose'],
          'change': meta['change'] ?? price['change'],
          'pChange': meta['pChange'] ?? price['pChange'],
          'weekHighLow': {
            'max': price['yearHigh'] ?? (price['weekHighLow'] is Map ? price['weekHighLow']['max'] : null),
            'min': price['yearLow'] ?? (price['weekHighLow'] is Map ? price['weekHighLow']['min'] : null),
          },
        },
        'orderBook': orderBook,
        'last': orderBook['lastPrice'] ?? trade['lastPrice'] ?? meta['closePrice'] ?? 0,
        'open': meta['open'] ?? trade['open'],
        'high': meta['dayHigh'] ?? (trade['intraDayHighLow'] is Map ? trade['intraDayHighLow']['max'] : null),
        'low': meta['dayLow'] ?? (trade['intraDayHighLow'] is Map ? trade['intraDayHighLow']['min'] : null),
        'previousClose': meta['previousClose'] ?? price['previousClose'],
        'timestamp': firstMap['lastUpdateTime'],
      };
    }

    if (res['equityResponse'] is Map) {
      return Map<String, dynamic>.from(res['equityResponse']);
    }

    return Map<String, dynamic>.from(res);
  }

  String get _displayName {
    return _quote?['info']?['companyName']?.toString() ??
        _quote?['metadata']?['companyName']?.toString() ??
        _symbol;
  }

  double get _lastPrice {
    if (_liveLastPrice > 0) {
      return _liveLastPrice;
    }

    final candidates = [
      _quote?['tradeInfo']?['lastPrice'],
      _quote?['priceInfo']?['lastPrice'],
      _quote?['metadata']?['lastPrice'],
      _quote?['last'],
    ];
    for (final value in candidates) {
      final n = (value as num?)?.toDouble() ?? double.tryParse(value?.toString() ?? '');
      if (n != null && n.isFinite) return n;
    }
    return 0;
  }

  double get _prevClose {
    final candidates = [
      _quote?['priceInfo']?['previousClose'],
      _quote?['previousClose'],
      _quote?['prev_close'],
    ];
    for (final value in candidates) {
      final n = (value as num?)?.toDouble() ?? double.tryParse(value?.toString() ?? '');
      if (n != null && n.isFinite) return n;
    }
    return 0;
  }

  double get _priceChange {
    final livePrice = _lastPrice;
    final prev = _prevClose;
    if (prev > 0 && livePrice > 0) return livePrice - prev;

    final direct = (_quote?['priceInfo']?['change'] as num?)?.toDouble() ??
        double.tryParse(_quote?['change']?.toString() ?? '');
    if (direct != null) return direct;

    return 0;
  }

  double get _pctChange {
    final livePrice = _lastPrice;
    final prev = _prevClose;
    if (prev > 0 && livePrice > 0) return ((_priceChange) / prev) * 100;

    final direct = (_quote?['priceInfo']?['pChange'] as num?)?.toDouble() ??
        double.tryParse(_quote?['percChange']?.toString() ?? '');
    if (direct != null) return direct;

    return 0;
  }

  bool get _isPositive => _priceChange >= 0;

  String get _quoteTime {
    return _quote?['metadata']?['lastUpdateTime']?.toString() ?? _quote?['timestamp']?.toString() ?? '--';
  }

  String _fmtNum(num? value, {int digits = 2}) {
    if (value == null) return '--';
    return NumberFormat.currency(locale: 'en_IN', symbol: '', decimalDigits: digits).format(value);
  }

  String _fmtIndian(num? value) {
    if (value == null) return '--';
    return NumberFormat.decimalPattern('en_IN').format(value);
  }

  String _fmtSigned(double value) {
    final sign = value >= 0 ? '+' : '';
    return '$sign${value.toStringAsFixed(2)}';
  }

  String get _liveStatusLabel {
    switch (_liveTransportStatus) {
      case _LiveTransportStatus.ws:
        return 'Live';
      case _LiveTransportStatus.polling:
        return 'Polling';
      case _LiveTransportStatus.connecting:
        return 'Connecting';
      case _LiveTransportStatus.closed:
        return 'Closed';
      case _LiveTransportStatus.idle:
        return 'Idle';
    }
  }

  Color _liveStatusColor(ThemeData theme) {
    switch (_liveTransportStatus) {
      case _LiveTransportStatus.ws:
        return AppTheme.successColor;
      case _LiveTransportStatus.polling:
      case _LiveTransportStatus.connecting:
        return Colors.amber.shade600;
      case _LiveTransportStatus.closed:
      case _LiveTransportStatus.idle:
        return theme.colorScheme.onSurfaceVariant;
    }
  }

  List<_PerfPoint> get _performanceCards {
    final p = _performance;
    if (p == null) return const [];

    double v(String key) => (p[key] as num?)?.toDouble() ?? double.tryParse(p[key]?.toString() ?? '') ?? 0;

    return [
      _PerfPoint('1W', v('one_week_chng_per'), v('index_one_week_chng_per')),
      _PerfPoint('1M', v('one_month_chng_per'), v('index_one_month_chng_per')),
      _PerfPoint('YTD', v('yesterday_chng_per'), v('index_yesterday_chng_per')),
      _PerfPoint('1Y', v('one_year_chng_per'), v('index_one_year_chng_per')),
      _PerfPoint('3Y', v('three_year_chng_per'), v('index_three_year_chng_per')),
      _PerfPoint('5Y', v('five_year_chng_per'), v('index_five_year_chng_per')),
    ];
  }

  Future<void> _openAttachment(String url) async {
    final uri = Uri.tryParse(url);
    if (uri == null) return;
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  }

  Future<void> _openAddHoldingDialog() async {
    final pageContext = context;
    bool dialogActive = true;
    final qtyCtrl = TextEditingController(text: '1');
    final avgCtrl = TextEditingController(
      text: _lastPrice > 0 ? _lastPrice.toStringAsFixed(2) : '',
    );
    bool saving = false;
    String formError = '';

    await showDialog<void>(
      context: context,
      builder: (ctx) {
        return StatefulBuilder(
          builder: (dialogContext, setModalState) {
            return AlertDialog(
              title: Text('Add $_symbol to Portfolio'),
              content: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  TextField(
                    controller: qtyCtrl,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                      labelText: 'Quantity',
                    ),
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    controller: avgCtrl,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(
                      labelText: 'Average Price',
                    ),
                  ),
                  if (formError.isNotEmpty) ...[
                    const SizedBox(height: 10),
                    Text(
                      formError,
                      style: TextStyle(color: Theme.of(dialogContext).colorScheme.error),
                    ),
                  ],
                ],
              ),
              actions: [
                TextButton(
                  onPressed: saving
                      ? null
                      : () {
                          dialogActive = false;
                          Navigator.pop(ctx);
                        },
                  child: const Text('Cancel'),
                ),
                FilledButton(
                  onPressed: saving
                      ? null
                      : () async {
                          final qty = int.tryParse(qtyCtrl.text.trim()) ?? 0;
                          final avgPrice = double.tryParse(avgCtrl.text.trim()) ?? 0;
                          if (qty <= 0 || avgPrice <= 0) {
                            if (!dialogActive) return;
                            setModalState(() => formError = 'Please enter a valid quantity and average price.');
                            return;
                          }

                          if (!dialogActive) return;
                          setModalState(() {
                            formError = '';
                            saving = true;
                          });

                          try {
                            await _portfolioService.addHolding(
                              symbol: _symbol,
                              instrumentType: 'EQUITY',
                              qty: qty,
                              avgPrice: avgPrice,
                            );

                            if (!mounted || !ctx.mounted) return;
                            if (Navigator.of(ctx).canPop()) {
                              dialogActive = false;
                              Navigator.of(ctx).pop();
                            }
                            if (!mounted) return;
                            WidgetsBinding.instance.addPostFrameCallback((_) {
                              if (!mounted) return;
                              ScaffoldMessenger.of(pageContext).showSnackBar(
                                SnackBar(
                                  content: Text('$_symbol added to portfolio.'),
                                  behavior: SnackBarBehavior.floating,
                                ),
                              );
                            });
                          } catch (e) {
                            if (!dialogActive || !ctx.mounted) return;
                            setModalState(() {
                              saving = false;
                              formError = e.toString().replaceAll('Exception: ', '');
                            });
                          }
                        },
                  child: Text(saving ? 'Adding...' : 'Add Holding'),
                ),
              ],
            );
          },
        );
      },
    );

    dialogActive = false;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final gainColor = AppTheme.successColor;
    final lossColor = AppTheme.errorColor;

    return Scaffold(
      appBar: AppBar(
        title: Text(_symbol),
        actions: [
          IconButton(
            tooltip: 'Add to portfolio',
            onPressed: _openAddHoldingDialog,
            icon: const Icon(Icons.playlist_add),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error.isNotEmpty
              ? Center(child: Text(_error))
              : RefreshIndicator(
                  onRefresh: _loadAll,
                  child: ListView(
                    padding: const EdgeInsets.all(16),
                    children: [
                      _buildQuoteCard(theme, gainColor, lossColor),
                      const SizedBox(height: 12),
                      _buildChartCard(theme, gainColor, lossColor),
                      const SizedBox(height: 12),
                      _buildMarketDepthCard(theme),
                      const SizedBox(height: 12),
                      _buildPerformanceCard(theme),
                      const SizedBox(height: 12),
                      _buildAnnouncementsCard(theme),
                    ],
                  ),
                ),
    );
  }

  Widget _buildQuoteCard(ThemeData theme, Color gainColor, Color lossColor) {
    final changeColor = _isPositive ? gainColor : lossColor;
    final companyName = _displayName.replaceAll(RegExp(r'\s+'), ' ').trim();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.primary.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(999),
                    ),
                    child: Text(
                      _symbol,
                      style: TextStyle(
                        color: theme.colorScheme.primary,
                        fontWeight: FontWeight.w700,
                        fontSize: 12,
                      ),
                    ),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    companyName,
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 20, height: 1.2, fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'As on $_quoteTime',
                    style: TextStyle(color: theme.colorScheme.onSurfaceVariant),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 12),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  'LAST PRICE',
                  style: TextStyle(
                    fontSize: 12,
                    color: theme.colorScheme.onSurfaceVariant,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  _fmtNum(_lastPrice),
                  style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w700),
                ),
                Text(
                  '${_fmtSigned(_priceChange)} (${_fmtSigned(_pctChange)}%)',
                  style: TextStyle(
                    color: changeColor,
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildChartCard(ThemeData theme, Color gainColor, Color lossColor) {
    final chartSurface = theme.cardTheme.color ?? theme.colorScheme.surface;
    final border = theme.brightness == Brightness.dark
        ? Colors.white.withValues(alpha: 0.12)
        : const Color(0xFFCBD5E1);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Live Candles',
              style: TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 8),
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: ChartTimeframe.values.map((tf) {
                  final active = _timeframe == tf;
                  return Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: ChoiceChip(
                      selected: active,
                      label: Text(tf.label),
                      selectedColor: theme.colorScheme.primaryContainer,
                      backgroundColor: theme.cardColor,
                      labelStyle: TextStyle(
                        color: active ? theme.colorScheme.onPrimaryContainer : theme.colorScheme.onSurface,
                        fontWeight: FontWeight.w600,
                      ),
                      onSelected: (_) => _onTimeframeChanged(tf),
                    ),
                  );
                }).toList(),
              ),
            ),
            if (_resolvedTimeframe == ChartTimeframe.daily) ...[
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: _dailyRanges.map((range) {
                  final selected = _dailyRange == range && !_historyMode;
                  return ChoiceChip(
                    selected: selected,
                    label: Text(range),
                    selectedColor: theme.colorScheme.primaryContainer,
                    backgroundColor: theme.cardColor,
                    labelStyle: TextStyle(
                      color: selected ? theme.colorScheme.onPrimaryContainer : theme.colorScheme.onSurface,
                      fontWeight: FontWeight.w600,
                    ),
                    onSelected: (_) => _setDailyRange(range),
                  );
                }).toList(),
              ),
            ],
            // Custom historical window — available for every interval so the
            // user can scroll back and view old data for any range.
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () => _pickDate(true),
                    icon: const Icon(Icons.event, size: 18),
                    label: Text(_customFrom == null
                        ? 'From date'
                        : DateFormat('dd MMM yyyy').format(_customFrom!)),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () => _pickDate(false),
                    icon: const Icon(Icons.event, size: 18),
                    label: Text(_customTo == null
                        ? 'To date'
                        : DateFormat('dd MMM yyyy').format(_customTo!)),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: ElevatedButton.icon(
                    onPressed: (_historyLoading || _customFrom == null || _customTo == null)
                        ? null
                        : _loadCustomHistory,
                    icon: _historyLoading
                        ? const SizedBox(
                            width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.history, size: 18),
                    label: const Text('View range'),
                  ),
                ),
                if (_historyMode || _customFrom != null || _customTo != null) ...[
                  const SizedBox(width: 8),
                  OutlinedButton.icon(
                    onPressed: _resetCustomDateRange,
                    icon: const Icon(Icons.bolt, size: 18),
                    label: const Text('Live'),
                  ),
                ],
              ],
            ),
            if (_historyNotice.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Row(
                  children: [
                    Icon(Icons.history, size: 14, color: theme.colorScheme.onSurfaceVariant),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        _historyNotice,
                        style: TextStyle(color: theme.colorScheme.onSurfaceVariant, fontSize: 12),
                      ),
                    ),
                  ],
                ),
              ),
            if (_customRangeError.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Text(
                  _customRangeError,
                  style: const TextStyle(color: AppTheme.errorColor),
                ),
              ),
            const SizedBox(height: 10),
            if (_chartError.isNotEmpty)
              Container(
                width: double.infinity,
                margin: const EdgeInsets.only(bottom: 8),
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: AppTheme.errorColor.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Text(
                  _chartError,
                  style: const TextStyle(color: AppTheme.errorColor),
                ),
              ),
            Builder(
              builder: (context) {
                final renderCandles = _buildRenderCandles(_displayCandles);
                final visibleCandles = _visibleCandles(renderCandles);
                final selected = (visibleCandles.isNotEmpty && _hoveredCandleIndex != null)
                    ? visibleCandles[_hoveredCandleIndex!.clamp(0, visibleCandles.length - 1)]
                    : (visibleCandles.isNotEmpty ? visibleCandles.last : null);

                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (selected != null)
                      Container(
                        width: double.infinity,
                        margin: const EdgeInsets.only(bottom: 8),
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                        decoration: BoxDecoration(
                          color: theme.brightness == Brightness.dark
                              ? const Color(0xFF111827)
                              : const Color(0xFFF8FAFC),
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(color: border),
                        ),
                        child: Wrap(
                          spacing: 12,
                          runSpacing: 6,
                          children: [
                            Text(
                              'O ${_fmtNum(selected.open)}',
                              style: TextStyle(
                                color: theme.colorScheme.onSurfaceVariant,
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            Text(
                              'H ${_fmtNum(selected.high)}',
                              style: TextStyle(color: gainColor, fontSize: 12, fontWeight: FontWeight.w700),
                            ),
                            Text(
                              'L ${_fmtNum(selected.low)}',
                              style: TextStyle(color: lossColor, fontSize: 12, fontWeight: FontWeight.w700),
                            ),
                            Text(
                              'C ${_fmtNum(selected.close)}',
                              style: TextStyle(color: theme.colorScheme.onSurface, fontSize: 12, fontWeight: FontWeight.w700),
                            ),
                          ],
                        ),
                      ),
                    SizedBox(
                      height: 320,
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          color: chartSurface,
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: border),
                        ),
                        child: _chartLoading
                            ? const Center(child: CircularProgressIndicator())
                            : visibleCandles.isEmpty
                                ? Center(
                                    child: Text(
                                      'No candle data available',
                                      style: TextStyle(color: theme.colorScheme.onSurfaceVariant),
                                    ),
                                  )
                                : LayoutBuilder(
                                    builder: (context, constraints) {
                                      return GestureDetector(
                                        behavior: HitTestBehavior.opaque,
                                        onScaleStart: (_) {
                                          _gestureStartZoom = _chartZoom;
                                        },
                                        onScaleUpdate: (details) {
                                          if (details.pointerCount >= 2) {
                                            final nextZoom = (_gestureStartZoom * details.scale).clamp(1.0, 8.0);
                                            if ((_chartZoom - nextZoom).abs() > 0.001) {
                                              setState(() => _chartZoom = nextZoom);
                                            }
                                          } else if (_chartZoom > 1.0) {
                                            final maxPan = math.max(0.0, renderCandles.length - 30.0);
                                            final nextPan = (_chartPanBars + (details.focalPointDelta.dx * -0.6)).clamp(0.0, maxPan);
                                            if ((_chartPanBars - nextPan).abs() > 0.1) {
                                              setState(() => _chartPanBars = nextPan);
                                            }
                                          }
                                          _updateHoveredCandle(details.localFocalPoint, constraints.maxWidth, visibleCandles);
                                        },
                                        onDoubleTap: _resetChartView,
                                        onLongPressStart: (details) => _updateHoveredCandle(details.localPosition, constraints.maxWidth, visibleCandles),
                                        onLongPressMoveUpdate: (details) => _updateHoveredCandle(details.localPosition, constraints.maxWidth, visibleCandles),
                                        onLongPressEnd: (_) => setState(() => _hoveredCandleIndex = null),
                                        child: Padding(
                                          padding: const EdgeInsets.all(8),
                                          child: RepaintBoundary(
                                            child: CustomPaint(
                                              painter: _CandlestickPainter(
                                                candles: visibleCandles,
                                                hoveredIndex: _hoveredCandleIndex,
                                                upColor: gainColor,
                                                downColor: lossColor,
                                                axisColor: theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.5),
                                                textColor: theme.colorScheme.onSurfaceVariant,
                                              ),
                                              size: Size.infinite,
                                            ),
                                          ),
                                        ),
                                      );
                                    },
                                  ),
                      ),
                    ),
                    if (renderCandles.length < _displayCandles.length)
                      Padding(
                        padding: const EdgeInsets.only(top: 6),
                        child: Text(
                          'Rendering ${renderCandles.length} of ${_displayCandles.length} candles for smooth performance.',
                          style: TextStyle(color: theme.colorScheme.onSurfaceVariant, fontSize: 11),
                        ),
                      ),
                  ],
                );
              },
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 10,
              runSpacing: 4,
              alignment: WrapAlignment.spaceBetween,
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(999),
                    border: Border.all(color: border),
                    color: theme.brightness == Brightness.dark
                        ? const Color(0xFF111827)
                        : const Color(0xFFF8FAFC),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        margin: const EdgeInsets.only(right: 6),
                        child: ScaleTransition(
                          scale: _liveTransportStatus == _LiveTransportStatus.ws
                              ? _livePulseAnimation
                              : const AlwaysStoppedAnimation<double>(1.0),
                          child: Container(
                            width: 7,
                            height: 7,
                            decoration: BoxDecoration(
                              color: _liveStatusColor(theme),
                              shape: BoxShape.circle,
                            ),
                          ),
                        ),
                      ),
                      Text(
                        _liveStatusLabel,
                        style: TextStyle(
                          color: theme.colorScheme.onSurfaceVariant,
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                ),
                Text(
                  'Candles: $_candleCount',
                  style: TextStyle(
                    color: theme.colorScheme.onSurfaceVariant,
                    fontSize: 12,
                  ),
                ),
                Text(
                  _chartUpdatedAt == null
                      ? 'Updated: --'
                      : 'Updated: ${DateFormat('dd MMM yyyy, hh:mm:ss a').format(_chartUpdatedAt!)}',
                  style: TextStyle(
                    color: theme.colorScheme.onSurfaceVariant,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildPerformanceCard(ThemeData theme) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Absolute Returns',
              style: TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 10),
            if (_performanceLoading)
              const Center(child: CircularProgressIndicator())
            else if (_performanceCards.isEmpty)
              Text(
                'Performance data unavailable.',
                style: TextStyle(color: theme.colorScheme.onSurfaceVariant),
              )
            else
              LayoutBuilder(
                builder: (context, constraints) {
                  final cardWidth = (constraints.maxWidth - 8) / 2;
                  return Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: _performanceCards.map((p) {
                      final stockColor = p.stock >= 0 ? AppTheme.successColor : AppTheme.errorColor;
                      final indexColor = p.index >= 0 ? AppTheme.successColor : AppTheme.errorColor;
                      return SizedBox(
                        width: cardWidth,
                        child: Container(
                          padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(
                            color: theme.brightness == Brightness.dark
                                ? const Color(0xFF0F172A)
                                : const Color(0xFFF8FAFC),
                            borderRadius: BorderRadius.circular(10),
                            border: Border.all(
                              color: theme.brightness == Brightness.dark
                                  ? Colors.white12
                                  : const Color(0xFFE2E8F0),
                            ),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(p.label, style: const TextStyle(fontWeight: FontWeight.w700)),
                              const SizedBox(height: 6),
                              Text(
                                'Stock: ${_fmtSigned(p.stock)}%',
                                style: TextStyle(color: stockColor, fontWeight: FontWeight.w700),
                              ),
                              const SizedBox(height: 2),
                              Text(
                                'Index: ${_fmtSigned(p.index)}%',
                                style: TextStyle(color: indexColor, fontWeight: FontWeight.w700),
                              ),
                            ],
                          ),
                        ),
                      );
                    }).toList(),
                  );
                },
              ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                _statTile('Open', _fmtNum((_quote?['tradeInfo']?['open'] as num?) ?? (_quote?['open'] as num?))),
                _statTile('High', _fmtNum((_quote?['tradeInfo']?['intraDayHighLow']?['max'] as num?) ?? (_quote?['high'] as num?))),
                _statTile('Low', _fmtNum((_quote?['tradeInfo']?['intraDayHighLow']?['min'] as num?) ?? (_quote?['low'] as num?))),
                _statTile('Prev Close', _fmtNum((_quote?['priceInfo']?['previousClose'] as num?) ?? (_quote?['previousClose'] as num?))),
                _statTile('Traded Volume', _fmtIndian((_quote?['tradeInfo']?['totalTradedVolume'] as num?))),
                _statTile('52W High', _fmtNum(_quote?['priceInfo']?['weekHighLow']?['max'] as num?)),
                _statTile('52W Low', _fmtNum(_quote?['priceInfo']?['weekHighLow']?['min'] as num?)),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildMarketDepthCard(ThemeData theme) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Market Depth',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 8),
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  ChoiceChip(
                    selected: _marketDepthLimit == 20,
                    label: const Text('Top 20', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
                    selectedColor: theme.colorScheme.primaryContainer,
                    backgroundColor: theme.cardColor,
                    labelStyle: TextStyle(
                      color: _marketDepthLimit == 20 ? theme.colorScheme.onPrimaryContainer : theme.colorScheme.onSurface,
                      fontWeight: FontWeight.w600,
                      fontSize: 12,
                    ),
                    onSelected: (_) => _setMarketDepthLimit(20),
                  ),
                  const SizedBox(width: 8),
                  ChoiceChip(
                    selected: _marketDepthLimit == 200,
                    label: const Text('View 200 Depth', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
                    selectedColor: theme.colorScheme.primaryContainer,
                    backgroundColor: theme.cardColor,
                    labelStyle: TextStyle(
                      color: _marketDepthLimit == 200 ? theme.colorScheme.onPrimaryContainer : theme.colorScheme.onSurface,
                      fontWeight: FontWeight.w600,
                      fontSize: 12,
                    ),
                    onSelected: (_) => _setMarketDepthLimit(200),
                  ),
                ],
              ),
            ),
            if (_marketDepthMode.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(
                _marketDepthMode == 'full_depth_ws' ? 'Mode: Full Depth WebSocket' : 'Mode: Snapshot Depth',
                style: TextStyle(color: theme.colorScheme.onSurfaceVariant, fontSize: 12),
              ),
            ],
            const SizedBox(height: 10),
            if (_marketDepthLoading)
              const Center(child: CircularProgressIndicator())
            else if (_marketDepthError.isNotEmpty)
              Text(_marketDepthError, style: const TextStyle(color: AppTheme.errorColor))
            else
              LayoutBuilder(
                builder: (context, constraints) {
                  final narrow = constraints.maxWidth < 640;
                  if (narrow) {
                    return Column(
                      children: [
                        _depthTable(
                          theme: theme,
                          title: 'Buy Orders',
                          rows: _marketDepthBuy,
                          priceColor: AppTheme.successColor,
                        ),
                        const SizedBox(height: 10),
                        _depthTable(
                          theme: theme,
                          title: 'Sell Orders',
                          rows: _marketDepthSell,
                          priceColor: AppTheme.errorColor,
                        ),
                      ],
                    );
                  }

                  return Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: _depthTable(
                          theme: theme,
                          title: 'Buy Orders',
                          rows: _marketDepthBuy,
                          priceColor: AppTheme.successColor,
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: _depthTable(
                          theme: theme,
                          title: 'Sell Orders',
                          rows: _marketDepthSell,
                          priceColor: AppTheme.errorColor,
                        ),
                      ),
                    ],
                  );
                },
              ),
          ],
        ),
      ),
    );
  }

  Widget _depthTable({
    required ThemeData theme,
    required String title,
    required List<DhanDepthLevel> rows,
    required Color priceColor,
  }) {
    final display = rows.take(10).toList();

    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: theme.brightness == Brightness.dark ? Colors.white12 : const Color(0xFFE2E8F0),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
          const SizedBox(height: 4),
          Row(
            children: [
              Expanded(
                child: Text(
                  'Ord',
                  textAlign: TextAlign.right,
                  style: TextStyle(fontSize: 11, color: theme.colorScheme.onSurfaceVariant),
                ),
              ),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  'Qty',
                  textAlign: TextAlign.right,
                  style: TextStyle(fontSize: 11, color: theme.colorScheme.onSurfaceVariant),
                ),
              ),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  'Price',
                  textAlign: TextAlign.right,
                  style: TextStyle(fontSize: 11, color: theme.colorScheme.onSurfaceVariant),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          ...display.map((row) {
            return Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      _fmtIndian(row.orders),
                      textAlign: TextAlign.right,
                      style: TextStyle(fontSize: 11, color: theme.colorScheme.onSurfaceVariant),
                    ),
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      _fmtIndian(row.quantity),
                      textAlign: TextAlign.right,
                      style: TextStyle(fontSize: 11, color: theme.colorScheme.onSurfaceVariant),
                    ),
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      _fmtNum(row.price),
                      textAlign: TextAlign.right,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(fontSize: 11, color: priceColor, fontWeight: FontWeight.w700),
                    ),
                  ),
                ],
              ),
            );
          }),
        ],
      ),
    );
  }

  Widget _statTile(String label, String value) {
    final theme = Theme.of(context);
    return SizedBox(
      width: 150,
      child: Container(
        padding: const EdgeInsets.all(9),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(10),
          color: theme.brightness == Brightness.dark
              ? const Color(0xFF111827)
              : const Color(0xFFF8FAFC),
          border: Border.all(
            color: theme.brightness == Brightness.dark ? Colors.white12 : const Color(0xFFE2E8F0),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label,
              style: TextStyle(fontSize: 11, color: theme.colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: 4),
            Text(
              value,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAnnouncementsCard(ThemeData theme) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Recent Announcements',
              style: TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 10),
            if (_announcementsLoading)
              const Center(child: CircularProgressIndicator())
            else if (_announcements.isEmpty)
              Text(
                'No recent announcements.',
                style: TextStyle(color: theme.colorScheme.onSurfaceVariant),
              )
            else
              ..._announcements.map((a) {
                return Container(
                  margin: const EdgeInsets.only(bottom: 8),
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(
                      color: theme.brightness == Brightness.dark ? Colors.white12 : const Color(0xFFE2E8F0),
                    ),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        a.subject,
                        style: const TextStyle(fontWeight: FontWeight.w700),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        a.broadcastDate,
                        style: TextStyle(
                          color: theme.colorScheme.onSurfaceVariant,
                          fontSize: 12,
                        ),
                      ),
                      if (a.attachmentLink.trim().isNotEmpty)
                        Align(
                          alignment: Alignment.centerRight,
                          child: TextButton.icon(
                            onPressed: () => _openAttachment(a.attachmentLink),
                            icon: const Icon(Icons.open_in_new, size: 16),
                            label: const Text('Open PDF'),
                          ),
                        ),
                    ],
                  ),
                );
              }),
          ],
        ),
      ),
    );
  }
}

class _ChartSnapshot {
  final DhanChartIdentity identity;
  final ChartTimeframe resolvedTimeframe;
  final List<DhanChartCandle> candles;
  final DateTime updatedAt;
  final double lastPrice;

  _ChartSnapshot({
    required this.identity,
    required this.resolvedTimeframe,
    required this.candles,
    required this.updatedAt,
    required this.lastPrice,
  });
}

class _PerfPoint {
  final String label;
  final double stock;
  final double index;

  const _PerfPoint(this.label, this.stock, this.index);
}

enum _LiveTransportStatus { idle, connecting, ws, polling, closed }

class _CandlestickPainter extends CustomPainter {
  final List<DhanChartCandle> candles;
  final int? hoveredIndex;
  final Color upColor;
  final Color downColor;
  final Color axisColor;
  final Color textColor;

  _CandlestickPainter({
    required this.candles,
    required this.hoveredIndex,
    required this.upColor,
    required this.downColor,
    required this.axisColor,
    required this.textColor,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (candles.isEmpty) return;

    const leftPad = 8.0;
    const rightPad = 52.0;
    const topPad = 10.0;
    const bottomPad = 20.0;

    final chartW = size.width - leftPad - rightPad;
    final chartH = size.height - topPad - bottomPad;
    if (chartW <= 0 || chartH <= 0) return;

    double minLow = candles.first.low;
    double maxHigh = candles.first.high;
    for (final c in candles) {
      minLow = math.min(minLow, c.low);
      maxHigh = math.max(maxHigh, c.high);
    }

    if ((maxHigh - minLow).abs() < 1e-9) {
      maxHigh += 1;
      minLow -= 1;
    }

    double yFor(double price) {
      final ratio = (price - minLow) / (maxHigh - minLow);
      return topPad + (1 - ratio) * chartH;
    }

    final axisPaint = Paint()
      ..color = axisColor
      ..strokeWidth = 1;
    canvas.drawLine(
      Offset(leftPad, topPad + chartH),
      Offset(leftPad + chartW, topPad + chartH),
      axisPaint,
    );

    final priceText = TextPainter(
      textDirection: TextDirection.ltr,
      maxLines: 1,
    );

    for (var i = 0; i <= 4; i++) {
      final value = minLow + (maxHigh - minLow) * (i / 4);
      final y = yFor(value);

      canvas.drawLine(
        Offset(leftPad, y),
        Offset(leftPad + chartW, y),
        axisPaint..color = axisColor.withValues(alpha: 0.35),
      );

      priceText.text = TextSpan(
        text: value.toStringAsFixed(2),
        style: TextStyle(color: textColor, fontSize: 10),
      );
      priceText.layout();
      priceText.paint(canvas, Offset(leftPad + chartW + 4, y - 6));
    }

    final step = chartW / candles.length;
    final candleW = math.max(2.0, math.min(10.0, step * 0.65));
    final wickPaint = Paint()..strokeWidth = 1.2;

    for (var i = 0; i < candles.length; i++) {
      final c = candles[i];
      final x = leftPad + i * step + step / 2;
      final openY = yFor(c.open);
      final closeY = yFor(c.close);
      final highY = yFor(c.high);
      final lowY = yFor(c.low);

      final bullish = c.close >= c.open;
      final color = bullish ? upColor : downColor;

      wickPaint.color = color;
      canvas.drawLine(Offset(x, highY), Offset(x, lowY), wickPaint);

      final bodyTop = math.min(openY, closeY);
      final bodyBottom = math.max(openY, closeY);
      final rect = Rect.fromLTRB(
        x - candleW / 2,
        bodyTop,
        x + candleW / 2,
        math.max(bodyTop + 1.5, bodyBottom),
      );

      final bodyPaint = Paint()
        ..color = color
        ..style = PaintingStyle.fill;
      canvas.drawRect(rect, bodyPaint);
    }

    if (hoveredIndex != null && hoveredIndex! >= 0 && hoveredIndex! < candles.length) {
      final i = hoveredIndex!;
      final stepX = chartW / candles.length;
      final x = leftPad + i * stepX + stepX / 2;
      final closeY = yFor(candles[i].close);

      final crossPaint = Paint()
        ..color = textColor.withValues(alpha: 0.45)
        ..strokeWidth = 1;
      canvas.drawLine(Offset(x, topPad), Offset(x, topPad + chartH), crossPaint);
      canvas.drawLine(Offset(leftPad, closeY), Offset(leftPad + chartW, closeY), crossPaint);

      final dotPaint = Paint()..color = textColor;
      canvas.drawCircle(Offset(x, closeY), 2.5, dotPaint);
    }

    final first = DateTime.fromMillisecondsSinceEpoch(candles.first.time * 1000, isUtc: true)
        .add(const Duration(hours: 5, minutes: 30));
    final last = DateTime.fromMillisecondsSinceEpoch(candles.last.time * 1000, isUtc: true)
        .add(const Duration(hours: 5, minutes: 30));

    final fmt = DateFormat('dd MMM');
    final leftLabel = TextPainter(
      text: TextSpan(
        text: fmt.format(first),
        style: TextStyle(color: textColor, fontSize: 10),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    final rightLabel = TextPainter(
      text: TextSpan(
        text: fmt.format(last),
        style: TextStyle(color: textColor, fontSize: 10),
      ),
      textDirection: TextDirection.ltr,
    )..layout();

    leftLabel.paint(canvas, Offset(leftPad, topPad + chartH + 4));
    rightLabel.paint(
      canvas,
      Offset(leftPad + chartW - rightLabel.width, topPad + chartH + 4),
    );
  }

  @override
  bool shouldRepaint(covariant _CandlestickPainter oldDelegate) {
    return oldDelegate.candles != candles ||
        oldDelegate.hoveredIndex != hoveredIndex ||
        oldDelegate.upColor != upColor ||
        oldDelegate.downColor != downColor ||
        oldDelegate.axisColor != axisColor ||
        oldDelegate.textColor != textColor;
  }
}
