import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import 'strategy_service.dart';
import 'dart:math' as math;

// ── Preset Definitions ──
class _PL { final String t, a; final int o; const _PL(this.t, this.a, this.o); }
class _Preset { final String name, cat; final List<_PL> legs; const _Preset(this.name, this.cat, this.legs); }

const _presets = <_Preset>[
  _Preset('Long Call','bullish',[_PL('CE','BUY',0)]),
  _Preset('Short Put','bullish',[_PL('PE','SELL',0)]),
  _Preset('Bull Call Spread','bullish',[_PL('CE','BUY',0),_PL('CE','SELL',1)]),
  _Preset('Bull Put Spread','bullish',[_PL('PE','SELL',0),_PL('PE','BUY',-1)]),
  _Preset('Call Ratio Back Spread','bullish',[_PL('CE','SELL',0),_PL('CE','BUY',1),_PL('CE','BUY',1)]),
  _Preset('Long Synthetic','bullish',[_PL('CE','BUY',0),_PL('PE','SELL',0)]),
  _Preset('Range Forward','bullish',[_PL('CE','BUY',1),_PL('PE','SELL',-1)]),
  _Preset('Bullish Butterfly','bullish',[_PL('CE','BUY',0),_PL('CE','SELL',1),_PL('CE','SELL',1),_PL('CE','BUY',2)]),
  _Preset('Bullish Condor','bullish',[_PL('CE','BUY',0),_PL('CE','SELL',1),_PL('CE','SELL',2),_PL('CE','BUY',3)]),
  _Preset('Short Call','bearish',[_PL('CE','SELL',0)]),
  _Preset('Long Put','bearish',[_PL('PE','BUY',0)]),
  _Preset('Bear Call Spread','bearish',[_PL('CE','SELL',0),_PL('CE','BUY',1)]),
  _Preset('Bear Put Spread','bearish',[_PL('PE','BUY',0),_PL('PE','SELL',-1)]),
  _Preset('Put Ratio Back Spread','bearish',[_PL('PE','SELL',0),_PL('PE','BUY',-1),_PL('PE','BUY',-1)]),
  _Preset('Short Synthetic','bearish',[_PL('PE','BUY',0),_PL('CE','SELL',0)]),
  _Preset('Risk Reversal','bearish',[_PL('PE','BUY',-1),_PL('CE','SELL',1)]),
  _Preset('Bearish Butterfly','bearish',[_PL('PE','BUY',0),_PL('PE','SELL',-1),_PL('PE','SELL',-1),_PL('PE','BUY',-2)]),
  _Preset('Bearish Condor','bearish',[_PL('PE','BUY',0),_PL('PE','SELL',-1),_PL('PE','SELL',-2),_PL('PE','BUY',-3)]),
  _Preset('Long Straddle','neutral',[_PL('CE','BUY',0),_PL('PE','BUY',0)]),
  _Preset('Short Straddle','neutral',[_PL('CE','SELL',0),_PL('PE','SELL',0)]),
  _Preset('Long Strangle','neutral',[_PL('CE','BUY',1),_PL('PE','BUY',-1)]),
  _Preset('Short Strangle','neutral',[_PL('CE','SELL',1),_PL('PE','SELL',-1)]),
  _Preset('Jade Lizard','neutral',[_PL('CE','SELL',1),_PL('CE','BUY',2),_PL('PE','SELL',-1)]),
  _Preset('Iron Fly','neutral',[_PL('PE','BUY',-1),_PL('PE','SELL',0),_PL('CE','SELL',0),_PL('CE','BUY',1)]),
  _Preset('Iron Condor','neutral',[_PL('PE','BUY',-2),_PL('PE','SELL',-1),_PL('CE','SELL',1),_PL('CE','BUY',2)]),
  _Preset('Call Ratio Spread','neutral',[_PL('CE','BUY',0),_PL('CE','SELL',1),_PL('CE','SELL',1)]),
  _Preset('Put Ratio Spread','neutral',[_PL('PE','BUY',0),_PL('PE','SELL',-1),_PL('PE','SELL',-1)]),
  _Preset('Batman','neutral',[_PL('PE','BUY',-3),_PL('PE','SELL',-2),_PL('PE','SELL',-1),_PL('PE','BUY',0),_PL('CE','BUY',0),_PL('CE','SELL',1),_PL('CE','SELL',2),_PL('CE','BUY',3)]),
  _Preset('Long Iron Fly','neutral',[_PL('PE','SELL',-1),_PL('PE','BUY',0),_PL('CE','BUY',0),_PL('CE','SELL',1)]),
  _Preset('Short Iron Fly','neutral',[_PL('PE','BUY',-1),_PL('PE','SELL',0),_PL('CE','SELL',0),_PL('CE','BUY',1)]),
  _Preset('Call Butterfly','neutral',[_PL('CE','BUY',-1),_PL('CE','SELL',0),_PL('CE','SELL',0),_PL('CE','BUY',1)]),
  _Preset('Put Butterfly','neutral',[_PL('PE','BUY',1),_PL('PE','SELL',0),_PL('PE','SELL',0),_PL('PE','BUY',-1)]),
];

// ── Mini payoff diagram painter ──
class _PayoffPainter extends CustomPainter {
  final _Preset preset;
  _PayoffPainter(this.preset);

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()..color = Colors.green..strokeWidth = 1.5..style = PaintingStyle.stroke;
    final zeroPaint = Paint()..color = Colors.grey.withValues(alpha: 0.3)..strokeWidth = 0.5;
    final midY = size.height / 2;
    canvas.drawLine(Offset(0, midY), Offset(size.width, midY), zeroPaint);

    // Generate mini payoff
    const steps = 30;
    final path = Path();
    for (int i = 0; i <= steps; i++) {
      double x = i / steps;
      double spot = -1.5 + x * 3; // -1.5 to 1.5
      double pnl = 0;
      for (final l in preset.legs) {
        double m = l.a == 'BUY' ? 1 : -1;
        double k = l.o.toDouble();
        if (l.t == 'CE') pnl += (math.max(0.0, spot - k) - 0.3) * m;
        else pnl += (math.max(0.0, k - spot) - 0.3) * m;
      }
      double px = x * size.width;
      double py = midY - pnl * size.height * 0.3;
      py = py.clamp(2, size.height - 2);
      if (i == 0) path.moveTo(px, py); else path.lineTo(px, py);
    }
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

// ── Main Screen ──
class StrategyBuilderScreen extends StatefulWidget {
  final String? initialSymbol;
  final List<StrategyPosition>? initialPositions;

  const StrategyBuilderScreen({
    super.key,
    this.initialSymbol,
    this.initialPositions,
  });
  @override
  State<StrategyBuilderScreen> createState() => _StrategyBuilderScreenState();
}

class _StrategyBuilderScreenState extends State<StrategyBuilderScreen> {
  final StrategyService _svc = StrategyService();

  List<String> _symbols = ['NIFTY','BANKNIFTY','FINNIFTY'];
  String _sym = 'NIFTY';
  double _spot = 0, _fut = 0;
  int _lot = 1;
  List<String> _expiries = [];
  String _chainExp = '';
  List<double> _strikes = [];
  List<dynamic> _chainData = [];
  bool _loading = true, _dataReady = false;
  List<StrategyPosition> _legs = [];
  List<StrategyPosition> _portfolioOptionPositions = [];
  bool _loadingPortfolioOptions = false;
  String _cat = 'bullish';
  double _maxP = 0, _maxL = 0;
  List<double> _bes = [];
  bool _appliedInitialPositions = false;

  // Search
  final _searchCtrl = TextEditingController(text: 'NIFTY');
  List<String> _filtered = [];
  bool _showSearch = false;

  static const _idx = ['NIFTY','BANKNIFTY','FINNIFTY','MIDCPNIFTY'];
  bool get _isIdx => _idx.contains(_sym.toUpperCase());

  @override
  void initState() {
    super.initState();
    final initial = widget.initialSymbol?.toUpperCase().trim();
    if (initial != null && initial.isNotEmpty) {
      _sym = initial;
      _searchCtrl.text = initial;
    }
    _loadSymbols();
  }

  @override
  void dispose() { _searchCtrl.dispose(); super.dispose(); }

  Future<void> _loadSymbols() async {
    try { final s = await _svc.getSymbols(); if (s.isNotEmpty) _symbols = s; } catch (_) {}
    _onSymChange();
  }

  Future<void> _onSymChange() async {
    setState(() { _loading = true; _dataReady = false; });
    try {
      // Fetch dropdowns first (fast)
      final dd = await _svc.getDropdowns(_sym);
      _expiries = List<String>.from(dd['expiryDates'] ?? dd['expiryDate'] ?? []);
      _lot = (dd['lotSize'] ?? 1) is int ? dd['lotSize'] ?? 1 : int.tryParse(dd['lotSize'].toString()) ?? 1;
      if (_expiries.isNotEmpty) _chainExp = _expiries.first;
      if (mounted) setState(() => _loading = false);

      // Fetch spot, futures, chain in parallel
      final futures = <Future>[
        _svc.getSymbolData(_sym),
        if (_expiries.isNotEmpty) _svc.getOptionChain(_sym, expiry: _chainExp),
        _svc.getFuturesData(_sym),
      ];
      final results = await Future.wait(futures, eagerError: false);

      // Parse spot
      final spotRes = results[0] as Map<String, dynamic>;
      if (_isIdx) {
        _spot = _toDouble(spotRes['last'] ?? spotRes['lastPrice']);
      } else {
        _spot = _toDouble(spotRes['tradeInfo']?['lastPrice'] ?? spotRes['priceInfo']?['lastPrice'] ?? spotRes['metadata']?['lastPrice'] ?? spotRes['lastPrice']);
      }

      // Parse chain
      if (results.length > 1 && results[1] != null) {
        final chainRes = results[1] as Map<String, dynamic>;
        _chainData = List<dynamic>.from(chainRes['filtered']?['data'] ?? chainRes['data'] ?? []);
        _strikes = _chainData.map<double>((d) => _toDouble(d['strikePrice'])).toList()..sort();
        // Fallback spot from chain
        if (_spot <= 0) _spot = _toDouble(chainRes['records']?['underlyingValue'] ?? chainRes['underlyingValue']);
      }

      // Parse futures
      if (results.length > 2 && results[2] != null) {
        final futRes = results[2] as Map<String, dynamic>;
        if (_isIdx) {
          _fut = _toDouble(futRes['nearestFuture']?['lastPrice']);
        } else {
          final d = futRes['data'];
          if (d is List && d.isNotEmpty) _fut = _toDouble(d[0]['lastPrice']);
          else _fut = _toDouble(futRes['lastPrice'] ?? futRes['tradeInfo']?['lastPrice']);
        }
      }
      if (_fut <= 0) _fut = _spot;

      _dataReady = true;
      await _loadPortfolioOptionPositions();
      _applyInitialPositionsIfNeeded();
      _calcMetrics();
    } catch (e) {
      debugPrint('Load error: $e');
    }
    if (mounted) setState(() => _loading = false);
  }

  void _applyInitialPositionsIfNeeded() {
    if (_appliedInitialPositions) {
      return;
    }

    final initialPositions = widget.initialPositions;
    if (initialPositions == null || initialPositions.isEmpty) {
      return;
    }

    _appliedInitialPositions = true;
    setState(() {
      _legs.addAll(initialPositions);
    });
  }

  Future<void> _loadPortfolioOptionPositions() async {
    setState(() {
      _loadingPortfolioOptions = true;
    });

    try {
      final positions = await _svc.getPortfolioOptionPositions(_sym);
      if (!mounted) return;
      setState(() {
        _portfolioOptionPositions = positions;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _portfolioOptionPositions = [];
      });
    } finally {
      if (mounted) {
        setState(() {
          _loadingPortfolioOptions = false;
        });
      }
    }
  }

  void _addPortfolioOptionToBuilder(StrategyPosition p) {
    setState(() {
      _legs.add(p.copyWith(segment: p.segment.isNotEmpty ? p.segment : 'OPTIDX'));
    });
    _calcMetrics();
  }

  double _toDouble(dynamic v) {
    if (v == null) return 0;
    if (v is num) return v.toDouble();
    return double.tryParse(v.toString()) ?? 0;
  }

  double _getLtp(double strike, String type) {
    for (final r in _chainData) {
      if (_toDouble(r['strikePrice']) == strike) return _toDouble(r[type]?['lastPrice']);
    }
    return 0;
  }

  double _pnlAt(double s) {
    double t = 0;
    for (final l in _legs) {
      final m = l.action == 'BUY' ? 1.0 : -1.0;
      double p;
      if (l.optionType == 'CE') { p = (math.max(0.0, s - (l.strike ?? 0)) - l.entryPrice) * m; }
      else if (l.optionType == 'PE') { p = (math.max(0.0, (l.strike ?? 0) - s) - l.entryPrice) * m; }
      else { p = (s - l.entryPrice) * m; }
      t += p * l.qty * _lot;
    }
    return t;
  }

  bool _isUnlimitedProfit = false;
  bool _isUnlimitedLoss = false;

  void _calcMetrics() {
    if (_spot <= 0 || _legs.isEmpty) { setState(() { _maxP = 0; _maxL = 0; _bes = []; _isUnlimitedProfit = false; _isUnlimitedLoss = false; }); return; }
    final range = _spot * 0.3;
    const n = 120;
    final step = (range * 2) / n;
    double mxP = -1e18, mxL = 1e18;
    List<double> bs = [];
    double? prev; double? prevS;
    for (int i = 0; i <= n; i++) {
      final s = (_spot - range) + (i * step);
      final t = _pnlAt(s);
      if (t > mxP) { mxP = t; }
      if (t < mxL) { mxL = t; }
      if (prev != null && ((prev <= 0 && t > 0) || (prev >= 0 && t < 0))) { bs.add((prevS! + s) / 2); }
      prev = t; prevS = s;
    }
    // Check edges for unlimited: if PnL is still increasing at extremes
    final farUp = _pnlAt(_spot * 2);
    final veryFarUp = _pnlAt(_spot * 3);
    final farDown = _pnlAt(_spot * 0.1);
    final veryFarDown = _pnlAt(1);
    _isUnlimitedProfit = (veryFarUp > farUp && farUp > mxP * 0.8) || (veryFarDown > farDown && farDown > mxP * 0.8);
    _isUnlimitedLoss = (veryFarUp < farUp && farUp < mxL * 0.8) || (veryFarDown < farDown && farDown < mxL * 0.8);
    setState(() { _maxP = mxP; _maxL = mxL; _bes = bs; });
  }

  void _applyPreset(_Preset p) {
    if (!_dataReady || _strikes.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Loading data... please wait'), duration: Duration(seconds: 1)));
      return;
    }
    double atm = _strikes.reduce((a, b) => (a - _spot).abs() < (b - _spot).abs() ? a : b);
    double step = _strikes.length >= 2 ? (_strikes[1] - _strikes[0]).abs() : 100;
    if (step <= 0) step = 100;

    // Build leg configs
    final legs = p.legs.map((l) {
      double sk = atm + l.o * step;
      if (_strikes.isNotEmpty) sk = _strikes.reduce((a, b) => (a - sk).abs() < (b - sk).abs() ? a : b);
      return {'type': l.t, 'action': l.a, 'strike': sk, 'ltp': _getLtp(sk, l.t)};
    }).toList();

    String selExp = _chainExp;
    int lotQ = 1;

    showModalBottomSheet(
      context: context, isScrollControlled: true, backgroundColor: Colors.transparent,
      builder: (ctx) => StatefulBuilder(builder: (bCtx, ss) => Container(
        constraints: BoxConstraints(maxHeight: MediaQuery.of(ctx).size.height * 0.85),
        decoration: BoxDecoration(color: Theme.of(ctx).scaffoldBackgroundColor, borderRadius: const BorderRadius.vertical(top: Radius.circular(24)), border: Border.all(color: Colors.white10)),
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Container(width: 40, height: 4, decoration: BoxDecoration(color: Colors.grey[700], borderRadius: BorderRadius.circular(2))),
            const SizedBox(height: 14),
            Text(p.name, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
            const SizedBox(height: 18),
            ...List.generate(legs.length, (i) {
              final lc = legs[i];
              return Padding(padding: const EdgeInsets.only(bottom: 10), child: Row(children: [
                SizedBox(width: 40, child: Text('${lc['action'] == 'BUY' ? '+' : '-'}1x', textAlign: TextAlign.center, style: TextStyle(fontWeight: FontWeight.w800, fontSize: 14, color: lc['action'] == 'BUY' ? Colors.green : Colors.red))),
                const SizedBox(width: 8),
                Expanded(child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  decoration: BoxDecoration(borderRadius: BorderRadius.circular(10), border: Border.all(color: Colors.white12), color: Colors.white.withValues(alpha: 0.04)),
                  child: DropdownButtonHideUnderline(child: DropdownButton<double>(
                    value: _strikes.contains(lc['strike'] as double) ? lc['strike'] as double : _strikes.first,
                    isExpanded: true, dropdownColor: Theme.of(ctx).scaffoldBackgroundColor,
                    style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: Colors.white),
                    items: _strikes.map((s) => DropdownMenuItem(value: s, child: Text(s.toStringAsFixed(0)))).toList(),
                    onChanged: (v) { if (v != null) ss(() { legs[i]['strike'] = v; legs[i]['ltp'] = _getLtp(v, lc['type'] as String); }); },
                  )),
                )),
                const SizedBox(width: 8),
                Text(lc['type'] as String, style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15, color: lc['type'] == 'CE' ? Colors.green : Colors.red)),
              ]));
            }),
            const SizedBox(height: 8),
            // Expiry
            Row(children: [
              const SizedBox(width: 70, child: Text('Expiry:', style: TextStyle(fontWeight: FontWeight.w600, color: Colors.grey))),
              Expanded(child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                decoration: BoxDecoration(borderRadius: BorderRadius.circular(10), border: Border.all(color: Colors.white12), color: Colors.white.withValues(alpha: 0.04)),
                child: DropdownButtonHideUnderline(child: DropdownButton<String>(
                  value: _expiries.contains(selExp) ? selExp : _expiries.first, isExpanded: true,
                  dropdownColor: Theme.of(ctx).scaffoldBackgroundColor,
                  items: _expiries.map((e) => DropdownMenuItem(value: e, child: Text(e, style: const TextStyle(fontSize: 14)))).toList(),
                  onChanged: (v) { if (v != null) ss(() => selExp = v); },
                )),
              )),
            ]),
            const SizedBox(height: 12),
            // Lot qty
            Row(children: [
              const SizedBox(width: 70, child: Text('Lots:', style: TextStyle(fontWeight: FontWeight.w600, color: Colors.grey))),
              Container(
                decoration: BoxDecoration(borderRadius: BorderRadius.circular(10), border: Border.all(color: Colors.white12)),
                child: Row(mainAxisSize: MainAxisSize.min, children: [
                  InkWell(onTap: () { if (lotQ > 1) ss(() => lotQ--); }, child: const SizedBox(width: 44, height: 40, child: Center(child: Text('−', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold))))),
                  Container(width: 44, height: 40, decoration: BoxDecoration(border: Border.symmetric(vertical: BorderSide(color: Colors.white12))), child: Center(child: Text('$lotQ', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)))),
                  InkWell(onTap: () => ss(() => lotQ++), child: const SizedBox(width: 44, height: 40, child: Center(child: Text('+', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold))))),
                ]),
              ),
            ]),
            const SizedBox(height: 14),
            // Prices
            Wrap(spacing: 6, runSpacing: 6, children: List.generate(legs.length, (i) => Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(borderRadius: BorderRadius.circular(8), border: Border.all(color: Colors.white10), color: Colors.white.withValues(alpha: 0.03)),
              child: Text('Leg ${i+1}: ₹${(legs[i]['ltp'] as double).toStringAsFixed(2)}', style: TextStyle(fontSize: 12, color: Colors.green[300], fontWeight: FontWeight.w600)),
            ))),
            const SizedBox(height: 18),
            SizedBox(width: double.infinity, height: 50, child: ElevatedButton(
              style: ElevatedButton.styleFrom(backgroundColor: legs.first['action'] == 'BUY' ? Colors.green : Colors.red, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14))),
              onPressed: () {
                setState(() {
                  _legs = legs.map((lc) => StrategyPosition(segment: 'OPTIDX', expiry: selExp, strike: lc['strike'] as double, optionType: lc['type'] as String, action: lc['action'] as String, qty: lotQ, entryPrice: (lc['ltp'] as double) > 0 ? lc['ltp'] as double : 0)).toList();
                  _calcMetrics();
                });
                Navigator.pop(ctx);
              },
              child: Text(legs.length > 1 ? 'ADD STRATEGY' : (legs.first['action'] as String), style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16, color: Colors.white)),
            )),
          ]),
        ),
      )),
    );
  }

  // ── BUILD ──
  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Strategy Builder', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 18)), actions: [
        IconButton(icon: const Icon(Icons.refresh, size: 22), onPressed: () { setState(() => _legs.clear()); _calcMetrics(); }),
      ]),
      body: _loading && !_dataReady
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(onRefresh: _onSymChange, child: ListView(padding: const EdgeInsets.only(bottom: 100), children: [
              _buildTopBar(theme),
              _buildPortfolioSync(theme),
              _buildPresets(theme),
              if (_legs.isNotEmpty) ...[_buildChart(theme), _buildStats(theme), _buildLegs(theme)],
              if (_chainData.isNotEmpty) _buildChain(theme),
            ])),
      floatingActionButton: FloatingActionButton.extended(onPressed: _showAddLeg, icon: const Icon(Icons.add), label: const Text('Add Leg')),
    );
  }

  Widget _buildTopBar(ThemeData theme) {
    return Container(
      margin: const EdgeInsets.fromLTRB(12, 8, 12, 0),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: theme.cardColor, borderRadius: BorderRadius.circular(14), border: Border.all(color: Colors.white10)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        // Searchable ticker
        const Text('TICKER', style: TextStyle(fontSize: 9, fontWeight: FontWeight.w800, color: Colors.grey, letterSpacing: 1.5)),
        const SizedBox(height: 4),
        TextField(
          controller: _searchCtrl,
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: theme.textTheme.bodyLarge?.color),
          decoration: const InputDecoration(border: InputBorder.none, isDense: true, contentPadding: EdgeInsets.zero, hintText: 'Search ticker...', hintStyle: TextStyle(color: Colors.grey)),
          textCapitalization: TextCapitalization.characters,
          onChanged: (q) { setState(() { _filtered = _symbols.where((s) => s.toUpperCase().contains(q.toUpperCase())).take(10).toList(); _showSearch = q.isNotEmpty && _filtered.isNotEmpty; }); },
          onTap: () { setState(() { _filtered = _symbols.take(10).toList(); _showSearch = true; }); },
        ),
        if (_showSearch) Container(
          constraints: const BoxConstraints(maxHeight: 200),
          decoration: BoxDecoration(color: theme.cardColor, borderRadius: BorderRadius.circular(8), border: Border.all(color: Colors.white12)),
          child: ListView.builder(
            shrinkWrap: true, itemCount: _filtered.length,
            itemBuilder: (_, i) => ListTile(
              dense: true, title: Text(_filtered[i], style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
              onTap: () { setState(() { _sym = _filtered[i]; _searchCtrl.text = _filtered[i]; _showSearch = false; }); _onSymChange(); },
            ),
          ),
        ),
        if (_spot > 0) ...[
          const SizedBox(height: 10),
          Row(children: [
            _chip('SPOT', '₹${_spot.toStringAsFixed(2)}', Colors.green),
            const SizedBox(width: 8),
            _chip('FUT', '₹${_fut.toStringAsFixed(2)}', Colors.blue),
            const SizedBox(width: 8),
            _chip('LOT', '$_lot', Colors.amber),
          ]),
        ],
      ]),
    );
  }

  Widget _buildPortfolioSync(ThemeData theme) {
    return Container(
      margin: const EdgeInsets.fromLTRB(12, 10, 12, 4),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: Colors.white10),
        color: theme.cardColor,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.sync_alt_rounded, size: 18),
              const SizedBox(width: 8),
              Text(
                'My Portfolio Options',
                style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: theme.colorScheme.onSurface),
              ),
              const Spacer(),
              if (_loadingPortfolioOptions)
                const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            _portfolioOptionPositions.isEmpty
                ? 'No option positions found in your portfolio for $_sym.'
                : '${_portfolioOptionPositions.length} synced position(s) available',
            style: TextStyle(fontSize: 12, color: theme.colorScheme.onSurface.withValues(alpha: 0.7)),
          ),
          if (_portfolioOptionPositions.isNotEmpty) ...[
            const SizedBox(height: 8),
            ..._portfolioOptionPositions.map((p) {
              return Container(
                margin: const EdgeInsets.only(bottom: 6),
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: Colors.white10),
                  color: Colors.white.withValues(alpha: 0.03),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        '${p.action} ${p.optionType} ${p.strike?.toStringAsFixed(0)} • ${p.expiry} • ${p.qty} lots',
                        style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600),
                      ),
                    ),
                    const SizedBox(width: 6),
                    TextButton(
                      onPressed: () => _addPortfolioOptionToBuilder(p),
                      child: const Text('Add'),
                    )
                  ],
                ),
              );
            }),
          ],
        ],
      ),
    );
  }

  Widget _chip(String label, String val, Color c) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
    decoration: BoxDecoration(color: c.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(8), border: Border.all(color: c.withValues(alpha: 0.3))),
    child: Column(children: [
      Text(label, style: TextStyle(fontSize: 8, fontWeight: FontWeight.w800, color: c, letterSpacing: 1)),
      Text(val, style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: c)),
    ]),
  );

  Widget _buildPresets(ThemeData theme) {
    final cats = ['bullish','bearish','neutral'];
    final clrs = {'bullish': Colors.green, 'bearish': Colors.red, 'neutral': Colors.grey};
    final fp = _presets.where((p) => p.cat == _cat).toList();
    return Container(
      margin: const EdgeInsets.fromLTRB(12, 10, 12, 0),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: theme.cardColor, borderRadius: BorderRadius.circular(14), border: Border.all(color: Colors.white10)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('STRATEGY PRESETS', style: TextStyle(fontSize: 9, fontWeight: FontWeight.w800, color: Colors.grey, letterSpacing: 1.5)),
        const SizedBox(height: 8),
        Container(
          padding: const EdgeInsets.all(3),
          decoration: BoxDecoration(borderRadius: BorderRadius.circular(10), color: Colors.white.withValues(alpha: 0.04)),
          child: Row(children: cats.map((c) {
            final on = _cat == c;
            return Expanded(child: GestureDetector(
              onTap: () => setState(() => _cat = c),
              child: Container(
                padding: const EdgeInsets.symmetric(vertical: 7),
                decoration: BoxDecoration(borderRadius: BorderRadius.circular(8), color: on ? clrs[c]!.withValues(alpha: 0.15) : Colors.transparent, border: on ? Border.all(color: clrs[c]!.withValues(alpha: 0.4)) : null),
                child: Text(c[0].toUpperCase() + c.substring(1), textAlign: TextAlign.center, style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: on ? clrs[c] : Colors.grey)),
              ),
            ));
          }).toList()),
        ),
        const SizedBox(height: 10),
        GridView.builder(
          shrinkWrap: true, physics: const NeverScrollableScrollPhysics(),
          gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(crossAxisCount: 3, childAspectRatio: 1.2, crossAxisSpacing: 8, mainAxisSpacing: 8),
          itemCount: fp.length,
          itemBuilder: (_, i) => Material(
            color: Colors.transparent,
            child: InkWell(
              onTap: () => _applyPreset(fp[i]),
              borderRadius: BorderRadius.circular(10),
              child: Container(
                padding: const EdgeInsets.all(6),
                decoration: BoxDecoration(borderRadius: BorderRadius.circular(10), border: Border.all(color: Colors.white10), color: Colors.white.withValues(alpha: 0.02)),
                child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                  SizedBox(height: 28, width: double.infinity, child: CustomPaint(painter: _PayoffPainter(fp[i]))),
                  const SizedBox(height: 4),
                  Text(fp[i].name, textAlign: TextAlign.center, style: const TextStyle(fontSize: 9, fontWeight: FontWeight.w600), maxLines: 2, overflow: TextOverflow.ellipsis),
                ]),
              ),
            ),
          ),
        ),
      ]),
    );
  }

  String _fmtOI(double oi) {
    if (oi >= 10000000) return '${(oi / 10000000).toStringAsFixed(1)}Cr';
    if (oi >= 100000) return '${(oi / 100000).toStringAsFixed(1)}L';
    if (oi >= 1000) return '${(oi / 1000).toStringAsFixed(1)}K';
    return oi.toInt().toString();
  }

  Widget _buildChart(ThemeData theme) {
    final range = _spot * 0.15;
    const n = 60;
    final step = (range * 2) / n;
    List<FlSpot> spots = [];
    for (int i = 0; i <= n; i++) {
      final s = (_spot - range) + (i * step);
      spots.add(FlSpot(s, _pnlAt(s)));
    }
    return Container(
      margin: const EdgeInsets.fromLTRB(12, 10, 12, 0),
      padding: const EdgeInsets.fromLTRB(4, 14, 14, 8),
      decoration: BoxDecoration(color: theme.cardColor, borderRadius: BorderRadius.circular(14), border: Border.all(color: Colors.white10)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Padding(padding: const EdgeInsets.only(left: 8, bottom: 6), child: Row(children: [
          const Text('PAYOFF DIAGRAM', style: TextStyle(fontSize: 9, fontWeight: FontWeight.w800, color: Colors.grey, letterSpacing: 1.5)),
          const Spacer(),
          Container(padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2), decoration: BoxDecoration(borderRadius: BorderRadius.circular(4), color: Colors.blue.withValues(alpha: 0.1)),
            child: Text('Spot: ${_spot.toStringAsFixed(0)}', style: TextStyle(fontSize: 9, fontWeight: FontWeight.w700, color: Colors.blue[300]))),
        ])),
        SizedBox(height: 220, child: LineChart(LineChartData(
          gridData: FlGridData(show: true, drawVerticalLine: false, getDrawingHorizontalLine: (_) => FlLine(color: Colors.white10, strokeWidth: 0.5)),
          titlesData: FlTitlesData(
            topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            bottomTitles: AxisTitles(axisNameWidget: const Text('Underlying Price →', style: TextStyle(fontSize: 8, color: Colors.grey)), sideTitles: SideTitles(showTitles: true, reservedSize: 22, interval: range * 0.5,
              getTitlesWidget: (v, _) => Text(v.toStringAsFixed(0), style: const TextStyle(fontSize: 8, color: Colors.grey)))),
            leftTitles: AxisTitles(axisNameWidget: const Text('P&L (₹)', style: TextStyle(fontSize: 8, color: Colors.grey)), sideTitles: SideTitles(showTitles: true, reservedSize: 40,
              getTitlesWidget: (v, _) => Text(_fmtOI(v), style: const TextStyle(fontSize: 8, color: Colors.grey)))),
          ),
          borderData: FlBorderData(show: false),
          lineTouchData: LineTouchData(
            touchTooltipData: LineTouchTooltipData(
              tooltipPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              getTooltipItems: (spots) => spots.map((s) {
                final pnl = s.y;
                final clr = pnl >= 0 ? Colors.green : Colors.red;
                return LineTooltipItem(
                  'Price: ${s.x.toStringAsFixed(0)}\nP&L: ₹${pnl.toStringAsFixed(0)}',
                  TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: clr),
                );
              }).toList(),
            ),
          ),
          lineBarsData: [LineChartBarData(spots: spots, isCurved: true, curveSmoothness: 0.2, color: Colors.green, barWidth: 2.5, dotData: const FlDotData(show: false),
            belowBarData: BarAreaData(show: true, gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [Colors.green.withValues(alpha: 0.15), Colors.transparent]), cutOffY: 0, applyCutOffY: true),
            aboveBarData: BarAreaData(show: true, gradient: LinearGradient(begin: Alignment.bottomCenter, end: Alignment.topCenter, colors: [Colors.red.withValues(alpha: 0.15), Colors.transparent]), cutOffY: 0, applyCutOffY: true),
          )],
          extraLinesData: ExtraLinesData(horizontalLines: [HorizontalLine(y: 0, color: Colors.grey.withValues(alpha: 0.4), strokeWidth: 1, dashArray: [5, 5])], verticalLines: [VerticalLine(x: _spot, color: Colors.blue.withValues(alpha: 0.4), strokeWidth: 1, dashArray: [5, 5])]),
        ))),
      ]),
    );
  }

  Widget _buildStats(ThemeData theme) {
    // Calculate extra metrics
    final absLoss = _maxL.abs();
    final rrRatio = (absLoss > 0 && !_isUnlimitedProfit && !_isUnlimitedLoss) ? (_maxP / absLoss) : 0.0;
    // Probability of Profit: % of price range where PnL > 0
    final range = _spot * 0.3;
    int profitCount = 0;
    const samples = 200;
    for (int i = 0; i <= samples; i++) {
      final s = (_spot - range) + (i * (range * 2) / samples);
      if (_pnlAt(s) > 0) profitCount++;
    }
    final pop = _legs.isNotEmpty ? (profitCount / (samples + 1) * 100) : 0.0;
    // Estimated margin: sum of entry premiums × qty × lot
    double margin = 0;
    for (final l in _legs) {
      if (l.action == 'SELL') { margin += l.entryPrice * l.qty * _lot; }
    }
    if (margin == 0) {
      for (final l in _legs) { margin += l.entryPrice * l.qty * _lot; }
    }

    return Column(children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(12, 10, 12, 0),
        child: Row(children: [
          Expanded(child: _stat('Max Profit', _isUnlimitedProfit ? 'Unlimited' : '₹${_maxP.toStringAsFixed(0)}', Colors.green)),
          const SizedBox(width: 6),
          Expanded(child: _stat('Max Loss', _isUnlimitedLoss ? 'Unlimited' : '₹${_maxL.toStringAsFixed(0)}', Colors.red)),
          const SizedBox(width: 6),
          Expanded(child: _stat('Breakeven', _bes.isEmpty ? '-' : _bes.map((e) => e.toStringAsFixed(0)).join(', '), Colors.blue)),
        ]),
      ),
      Padding(
        padding: const EdgeInsets.fromLTRB(12, 6, 12, 0),
        child: Row(children: [
          Expanded(child: _stat('RR Ratio', _isUnlimitedProfit ? '∞' : (rrRatio > 0 ? '1:${rrRatio.toStringAsFixed(2)}' : '-'), Colors.purple)),
          const SizedBox(width: 6),
          Expanded(child: _stat('Prob. of Profit', _legs.isEmpty ? '-' : '${pop.toStringAsFixed(1)}%', Colors.teal)),
          const SizedBox(width: 6),
          Expanded(child: _stat('Est. Margin', margin > 0 ? '₹${margin.toStringAsFixed(0)}' : '-', Colors.orange)),
        ]),
      ),
    ]);
  }

  Widget _stat(String l, String v, Color c) => Container(
    padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 6),
    decoration: BoxDecoration(color: c.withValues(alpha: 0.06), borderRadius: BorderRadius.circular(10), border: Border.all(color: c.withValues(alpha: 0.2))),
    child: Column(children: [
      Text(l, style: TextStyle(fontSize: 8, fontWeight: FontWeight.w700, color: Colors.grey[500], letterSpacing: 0.5)),
      const SizedBox(height: 2),
      Text(v, style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: c), overflow: TextOverflow.ellipsis, maxLines: 1),
    ]),
  );

  Widget _buildLegs(ThemeData theme) => Container(
    margin: const EdgeInsets.fromLTRB(12, 10, 12, 0),
    padding: const EdgeInsets.all(12),
    decoration: BoxDecoration(color: theme.cardColor, borderRadius: BorderRadius.circular(14), border: Border.all(color: Colors.white10)),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('POSITION LEGS', style: TextStyle(fontSize: 9, fontWeight: FontWeight.w800, color: Colors.grey, letterSpacing: 1.5)),
      const SizedBox(height: 8),
      ...List.generate(_legs.length, (i) {
        final l = _legs[i]; final buy = l.action == 'BUY';
        return Dismissible(key: UniqueKey(), direction: DismissDirection.endToStart,
          background: Container(alignment: Alignment.centerRight, padding: const EdgeInsets.only(right: 20), decoration: BoxDecoration(color: Colors.red.withValues(alpha: 0.15), borderRadius: BorderRadius.circular(10)), child: const Icon(Icons.delete, color: Colors.red)),
          onDismissed: (_) { setState(() { _legs.removeAt(i); _calcMetrics(); }); },
          child: Container(
            margin: const EdgeInsets.only(bottom: 6), padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
            decoration: BoxDecoration(borderRadius: BorderRadius.circular(10), border: Border.all(color: (buy ? Colors.green : Colors.red).withValues(alpha: 0.2)), color: (buy ? Colors.green : Colors.red).withValues(alpha: 0.04)),
            child: Row(children: [
              Container(padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3), decoration: BoxDecoration(color: (buy ? Colors.green : Colors.red).withValues(alpha: 0.12), borderRadius: BorderRadius.circular(5)),
                child: Text(l.action, style: TextStyle(fontSize: 10, fontWeight: FontWeight.w800, color: buy ? Colors.green : Colors.red))),
              const SizedBox(width: 8),
              Expanded(child: Text('${l.qty}x ${l.strike?.toStringAsFixed(0) ?? ""} ${l.optionType ?? ""}', style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13))),
              Text('₹${l.entryPrice.toStringAsFixed(2)}', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 13, color: Colors.grey[400])),
            ]),
          ),
        );
      }),
    ]),
  );

  Widget _buildChain(ThemeData theme) {
    const hdr = TextStyle(fontSize: 9, fontWeight: FontWeight.w800, color: Colors.grey, letterSpacing: 0.8);
    const cellS = TextStyle(fontSize: 10, fontWeight: FontWeight.w500);
    final stepHalf = _strikes.length >= 2 ? (_strikes[1] - _strikes[0]).abs() / 2 : 50.0;
    return Container(
      margin: const EdgeInsets.fromLTRB(12, 10, 12, 0),
      decoration: BoxDecoration(color: theme.cardColor, borderRadius: BorderRadius.circular(14), border: Border.all(color: Colors.white10)),
      child: Column(children: [
        Padding(padding: const EdgeInsets.all(12), child: Row(children: [
          const Text('OPTION CHAIN', style: TextStyle(fontSize: 9, fontWeight: FontWeight.w800, color: Colors.grey, letterSpacing: 1.5)),
          const Spacer(),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            decoration: BoxDecoration(borderRadius: BorderRadius.circular(8), border: Border.all(color: Colors.white12)),
            child: DropdownButtonHideUnderline(child: DropdownButton<String>(
              value: _expiries.contains(_chainExp) ? _chainExp : (_expiries.isNotEmpty ? _expiries.first : null), isDense: true,
              dropdownColor: theme.scaffoldBackgroundColor, style: const TextStyle(fontSize: 12),
              items: _expiries.map((e) => DropdownMenuItem(value: e, child: Text(e))).toList(),
              onChanged: (v) { if (v != null) { setState(() => _chainExp = v); _loadChainOnly(); } },
            )),
          ),
        ])),
        // Sticky header + scrollable body
        SizedBox(
          height: 450,
          child: Column(children: [
            // Fixed header row
            Container(
              padding: const EdgeInsets.symmetric(vertical: 6),
              decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.03), border: Border(bottom: BorderSide(color: Colors.white.withValues(alpha: 0.08)))),
              child: Row(children: [
                _chainHdr('OI', 1, hdr),
                _chainHdr('IV', 1, hdr),
                _chainHdr('LTP', 1, hdr, color: Colors.green),
                _chainHdr('STRIKE', 1, hdr, bold: true),
                _chainHdr('LTP', 1, hdr, color: Colors.red),
                _chainHdr('IV', 1, hdr),
                _chainHdr('OI', 1, hdr),
              ]),
            ),
            // Scrollable rows
            Expanded(child: ListView.builder(
              itemCount: _chainData.length,
              itemBuilder: (_, i) {
                final r = _chainData[i];
                final sk = _toDouble(r['strikePrice']);
                final isAtm = _spot > 0 && (sk - _spot).abs() < stepHalf;
                final ceOI = _toDouble(r['CE']?['openInterest']) * _lot;
                final peOI = _toDouble(r['PE']?['openInterest']) * _lot;
                final ceIV = _toDouble(r['CE']?['impliedVolatility']);
                final peIV = _toDouble(r['PE']?['impliedVolatility']);
                final ceLtp = _toDouble(r['CE']?['lastPrice']);
                final peLtp = _toDouble(r['PE']?['lastPrice']);
                final isITMce = sk < _spot;
                final isITMpe = sk > _spot;
                return Container(
                  decoration: BoxDecoration(
                    color: isAtm ? Colors.amber.withValues(alpha: 0.08) : null,
                    border: Border(bottom: BorderSide(color: Colors.white.withValues(alpha: 0.04))),
                  ),
                  child: Row(children: [
                    _chainCell(_fmtOI(ceOI), 1, cellS, bg: isITMce ? Colors.amber.withValues(alpha: 0.04) : null),
                    _chainCell(ceIV > 0 ? ceIV.toStringAsFixed(1) : '-', 1, cellS.copyWith(color: Colors.orange[300]), bg: isITMce ? Colors.amber.withValues(alpha: 0.04) : null),
                    _chainCell(ceLtp > 0 ? ceLtp.toStringAsFixed(2) : '-', 1, cellS.copyWith(fontWeight: FontWeight.bold, color: Colors.green), onTap: () => _addFromChain(r, 'CE'), bg: isITMce ? Colors.amber.withValues(alpha: 0.04) : null),
                    _chainCell(sk.toStringAsFixed(0), 1, TextStyle(fontSize: 10, fontWeight: FontWeight.w900, color: isAtm ? Colors.amber : Colors.white70)),
                    _chainCell(peLtp > 0 ? peLtp.toStringAsFixed(2) : '-', 1, cellS.copyWith(fontWeight: FontWeight.bold, color: Colors.red), onTap: () => _addFromChain(r, 'PE'), bg: isITMpe ? Colors.amber.withValues(alpha: 0.04) : null),
                    _chainCell(peIV > 0 ? peIV.toStringAsFixed(1) : '-', 1, cellS.copyWith(color: Colors.orange[300]), bg: isITMpe ? Colors.amber.withValues(alpha: 0.04) : null),
                    _chainCell(_fmtOI(peOI), 1, cellS, bg: isITMpe ? Colors.amber.withValues(alpha: 0.04) : null),
                  ]),
                );
              },
            )),
          ]),
        ),
      ]),
    );
  }

  Widget _chainHdr(String text, int flex, TextStyle style, {Color? color, bool bold = false}) {
    return Expanded(flex: flex, child: Text(text, textAlign: TextAlign.center, style: style.copyWith(color: color ?? style.color, fontWeight: bold ? FontWeight.w900 : style.fontWeight)));
  }

  Widget _chainCell(String text, int flex, TextStyle style, {VoidCallback? onTap, Color? bg}) {
    return Expanded(flex: flex, child: GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 8),
        color: bg,
        child: Text(text, textAlign: TextAlign.center, style: style),
      ),
    ));
  }

  Future<void> _loadChainOnly() async {
    try {
      final res = await _svc.getOptionChain(_sym, expiry: _chainExp);
      _chainData = List<dynamic>.from(res['filtered']?['data'] ?? res['data'] ?? []);
      _strikes = _chainData.map<double>((d) => _toDouble(d['strikePrice'])).toList()..sort();
      if (mounted) setState(() {});
    } catch (_) {}
  }

  void _addFromChain(dynamic row, String type) {
    final strike = _toDouble(row['strikePrice']);
    final ltp = _toDouble(row[type]?['lastPrice']);
    setState(() {
      _legs.add(StrategyPosition(segment: 'OPTIDX', expiry: _chainExp, strike: strike, optionType: type, action: 'BUY', qty: 1, entryPrice: ltp));
      _calcMetrics();
    });
  }

  void _showAddLeg() {
    String type = 'CE', action = 'BUY', expiry = _chainExp;
    double strike = _strikes.isNotEmpty ? _strikes[_strikes.length ~/ 2] : 0;
    int lotQty = 1;
    // Local chain data for the selected expiry (starts from main chain)
    List<dynamic> localChain = List.from(_chainData);
    bool loadingChain = false;

    double getLocalLtp(double sk, String tp) {
      for (final r in localChain) {
        if (_toDouble(r['strikePrice']) == sk) return _toDouble(r[tp]?['lastPrice']);
      }
      return 0;
    }

    showModalBottomSheet(context: context, isScrollControlled: true, backgroundColor: Colors.transparent, builder: (ctx) =>
      StatefulBuilder(builder: (_, ss) {
        double ltp = getLocalLtp(strike, type);
        return Container(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
          decoration: BoxDecoration(color: Theme.of(ctx).scaffoldBackgroundColor, borderRadius: const BorderRadius.vertical(top: Radius.circular(24)), border: Border.all(color: Colors.white10)),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Container(width: 40, height: 4, decoration: BoxDecoration(color: Colors.grey[700], borderRadius: BorderRadius.circular(2))),
            const SizedBox(height: 14),
            const Text('Add Position', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 16),
            // Action toggle
            Row(children: ['BUY','SELL'].map((a) { final on = action == a;
              return Expanded(child: GestureDetector(onTap: () => ss(() => action = a), child: Container(
                margin: EdgeInsets.only(right: a == 'BUY' ? 4 : 0, left: a == 'SELL' ? 4 : 0), padding: const EdgeInsets.symmetric(vertical: 10),
                decoration: BoxDecoration(borderRadius: BorderRadius.circular(10), color: on ? (a == 'BUY' ? Colors.green : Colors.red).withValues(alpha: 0.15) : Colors.white.withValues(alpha: 0.04), border: Border.all(color: on ? (a == 'BUY' ? Colors.green : Colors.red).withValues(alpha: 0.5) : Colors.white12)),
                child: Text(a, textAlign: TextAlign.center, style: TextStyle(fontWeight: FontWeight.w700, color: on ? (a == 'BUY' ? Colors.green : Colors.red) : Colors.grey)),
              ))); }).toList()),
            const SizedBox(height: 10),
            // Type toggle
            Row(children: ['CE','PE'].map((t) { final on = type == t;
              return Expanded(child: GestureDetector(onTap: () => ss(() => type = t), child: Container(
                margin: EdgeInsets.only(right: t == 'CE' ? 4 : 0, left: t == 'PE' ? 4 : 0), padding: const EdgeInsets.symmetric(vertical: 10),
                decoration: BoxDecoration(borderRadius: BorderRadius.circular(10), color: on ? (t == 'CE' ? Colors.green : Colors.red).withValues(alpha: 0.1) : Colors.white.withValues(alpha: 0.04), border: Border.all(color: on ? (t == 'CE' ? Colors.green : Colors.red).withValues(alpha: 0.4) : Colors.white12)),
                child: Text(t, textAlign: TextAlign.center, style: TextStyle(fontWeight: FontWeight.w700, color: on ? (t == 'CE' ? Colors.green : Colors.red) : Colors.grey)),
              ))); }).toList()),
            const SizedBox(height: 10),
            // Strike dropdown
            if (_strikes.isNotEmpty) Container(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              decoration: BoxDecoration(borderRadius: BorderRadius.circular(10), border: Border.all(color: Colors.white12), color: Colors.white.withValues(alpha: 0.04)),
              child: DropdownButtonHideUnderline(child: DropdownButton<double>(
                value: _strikes.contains(strike) ? strike : _strikes.first, isExpanded: true,
                items: _strikes.map((s) => DropdownMenuItem(value: s, child: Text('Strike: ${s.toStringAsFixed(0)}'))).toList(),
                onChanged: (v) { if (v != null) ss(() => strike = v); },
              )),
            ),
            const SizedBox(height: 10),
            // Expiry dropdown (fetches new chain on change)
            if (_expiries.isNotEmpty) Container(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              decoration: BoxDecoration(borderRadius: BorderRadius.circular(10), border: Border.all(color: Colors.white12), color: Colors.white.withValues(alpha: 0.04)),
              child: DropdownButtonHideUnderline(child: DropdownButton<String>(
                value: _expiries.contains(expiry) ? expiry : _expiries.first, isExpanded: true,
                items: _expiries.map((e) => DropdownMenuItem(value: e, child: Text('Expiry: $e', style: const TextStyle(fontSize: 14)))).toList(),
                onChanged: (v) {
                  if (v == null) return;
                  ss(() { expiry = v; loadingChain = true; });
                  _svc.getOptionChain(_sym, expiry: v).then((res) {
                    final data = List<dynamic>.from(res['filtered']?['data'] ?? res['data'] ?? []);
                    ss(() { localChain = data; loadingChain = false; });
                  }).catchError((_) { ss(() => loadingChain = false); return null; });
                },
              )),
            ),
            const SizedBox(height: 10),
            // Lot Qty selector + LTP
            Row(children: [
              const Text('Lots: ', style: TextStyle(fontWeight: FontWeight.w600, color: Colors.grey, fontSize: 14)),
              const SizedBox(width: 8),
              Container(
                decoration: BoxDecoration(borderRadius: BorderRadius.circular(10), border: Border.all(color: Colors.white12)),
                child: Row(mainAxisSize: MainAxisSize.min, children: [
                  InkWell(onTap: () { if (lotQty > 1) ss(() => lotQty--); }, child: const SizedBox(width: 40, height: 36, child: Center(child: Text('−', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold))))),
                  Container(width: 40, height: 36, decoration: BoxDecoration(border: Border.symmetric(vertical: BorderSide(color: Colors.white12))), child: Center(child: Text('$lotQty', style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold)))),
                  InkWell(onTap: () => ss(() => lotQty++), child: const SizedBox(width: 40, height: 36, child: Center(child: Text('+', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold))))),
                ]),
              ),
              const Spacer(),
              if (loadingChain) const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
              else if (ltp > 0) Text('LTP: ₹${ltp.toStringAsFixed(2)}', style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold, color: Colors.green[400])),
            ]),
            const SizedBox(height: 16),
            SizedBox(width: double.infinity, height: 48, child: ElevatedButton(
              style: ElevatedButton.styleFrom(backgroundColor: action == 'BUY' ? Colors.green : Colors.red, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14))),
              onPressed: () { setState(() { _legs.add(StrategyPosition(segment: 'OPTIDX', expiry: expiry, strike: strike, optionType: type, action: action, qty: lotQty, entryPrice: ltp > 0 ? ltp : 0)); _calcMetrics(); }); Navigator.pop(ctx); },
              child: Text('$action $type', style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16, color: Colors.white)),
            )),
          ]),
        );
      }),
    );
  }
}
