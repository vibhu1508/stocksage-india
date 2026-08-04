import 'package:flutter/material.dart';
import '../../config/theme.dart';
import '../../core/models/fo_data.dart';
import '../../core/services/fo_service.dart';
import '../../core/services/auth_service.dart';
import '../../shared/widgets/profile_menu.dart';
import '../profile/profile_screen.dart';
import '../strategy_builder/strategy_builder_screen.dart';

class FOAnalysisScreen extends StatefulWidget {
  final AuthService authService;

  const FOAnalysisScreen({super.key, required this.authService});

  @override
  State<FOAnalysisScreen> createState() => _FOAnalysisScreenState();
}

class _FOAnalysisScreenState extends State<FOAnalysisScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;

  bool _loading = false;
  String? _error;

  // Momentum tab
  Map<String, dynamic>? _momentumData;
  String _momentumExpiry = '';
  List<String> _momentumExpiries = [];
  List<dynamic> _top10 = [];
  List<dynamic> _bottom10 = [];
  List<dynamic> _shortCovering = [];
  List<dynamic> _longUnwinding = [];

  // NIFTY tab
  NiftyData? _niftyData;
  String _niftySymbol = 'NIFTY';
  String _niftyExpiry = '';

  // Futures tab
  FuturesTableData? _futuresTable;
  String _futuresSegment = 'index';
  String _futuresExpiry = '';
  String _futuresSymbol = '';

  // Options tab
  OptionChainData? _optionsData;
  String _optionsSymbol = 'NIFTY';
  String _optionsExpiry = '';

  /// Largest CE/PE open interest in the chain on screen - scales the OI bars.
  double _maxChainOi = 1;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 4, vsync: this);
    _tabController.addListener(() {
      if (!_tabController.indexIsChanging) {
        setState(() {}); // refresh appbar & date display
        _onTabChange(_tabController.index);
      }
    });
    _loadMomentumData();
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  void _onTabChange(int index) {
    setState(() => _error = null);
    switch (index) {
      case 0:
        if (_momentumData == null) _loadMomentumData();
        break;
      case 1:
        if (_niftyData == null) {
          _loadNiftyData();
        } else {
          _setMaxChainOi(_niftyData!.chain);
        }
        break;
      case 2:
        if (_futuresTable == null) _loadFuturesData();
        break;
      case 3:
        if (_optionsData == null) {
          _loadOptionsData();
        } else {
          _setMaxChainOi(_optionsData!.chain);
        }
        break;
    }
  }

  void _refreshActiveTab() {
    switch (_tabController.index) {
      case 0:
        _loadMomentumData();
        break;
      case 1:
        _loadNiftyData();
        break;
      case 2:
        _loadFuturesData();
        break;
      case 3:
        _loadOptionsData();
        break;
    }
  }

  void _setMaxChainOi(List<OptionChainRow> chain) {
    var maxOi = 1.0;
    for (final row in chain) {
      maxOi = [maxOi, row.ceOi ?? 0, row.peOi ?? 0].reduce((a, b) => a > b ? a : b);
    }
    _maxChainOi = maxOi;
  }

  void _startLoad() {
    setState(() {
      _loading = true;
      _error = null;
    });
  }

  void _failLoad(Object e) {
    setState(() {
      _error = e.toString().replaceAll('Exception: ', '');
      _loading = false;
    });
  }

  Future<void> _loadMomentumData() async {
    _startLoad();
    try {
      final data = await FOService.getFuturesAnalysis(
        null,
        expiry: _momentumExpiry,
      );
      setState(() {
        _momentumData = data;
        _momentumExpiries = List<String>.from(data['available_expiries'] ?? []);
        if (_momentumExpiry.isEmpty) {
          _momentumExpiry = (data['expiry_date'] ?? '').toString();
        }
        _top10 = data['top_10'] ?? [];
        _bottom10 = data['bottom_10'] ?? [];
        _shortCovering = data['short_covering'] ?? [];
        _longUnwinding = data['long_unwinding'] ?? [];
        _loading = false;
      });
    } catch (e) {
      _failLoad(e);
    }
  }

  Future<void> _loadNiftyData() async {
    _startLoad();
    try {
      final data = await FOService.getNiftyData(
        null, // auto-detect latest market date
        symbol: _niftySymbol,
        expiry: _niftyExpiry,
      );
      setState(() {
        _niftyData = data;
        _niftySymbol = data.symbol;
        _niftyExpiry = data.expiry ?? '';
        _setMaxChainOi(data.chain);
        _loading = false;
      });
    } catch (e) {
      setState(() => _niftyData = null);
      _failLoad(e);
    }
  }

  Future<void> _loadFuturesData() async {
    _startLoad();
    try {
      final data = await FOService.getFuturesTable(
        _futuresSegment,
        expiry: _futuresExpiry,
        symbol: _futuresSymbol,
      );
      setState(() {
        _futuresTable = data;
        _futuresExpiry = data.expiry ?? '';
        _futuresSymbol = data.symbol ?? '';
        _loading = false;
      });
    } catch (e) {
      setState(() => _futuresTable = null);
      _failLoad(e);
    }
  }

  Future<void> _loadOptionsData() async {
    _startLoad();
    try {
      final data = await FOService.getOptionsData(
        _optionsSymbol,
        null, // auto-detect latest market date
        expiry: _optionsExpiry,
      );
      setState(() {
        _optionsData = data;
        _optionsExpiry = data.expiry ?? '';
        _setMaxChainOi(data.chain);
        _loading = false;
      });
    } catch (e) {
      setState(() => _optionsData = null);
      _failLoad(e);
    }
  }

  String get _dataDate =>
      (_momentumData?['date'] ??
              _niftyData?.date ??
              _futuresTable?.date ??
              _optionsData?.date ??
              'Latest')
          .toString();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('F&O Analysis'),
        actions: [
          ProfileMenu(
            authService: widget.authService,
            onOpenProfile: () {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => ProfileScreen(authService: widget.authService),
                ),
              );
            },
          ),
          IconButton(
            icon: const Icon(Icons.add_chart),
            tooltip: 'Strategy Builder',
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (context) => const StrategyBuilderScreen(),
                ),
              );
            },
          ),
          IconButton(
            icon: Icon(Icons.refresh),
            onPressed: _refreshActiveTab,
          ),
        ],
        bottom: TabBar(
          controller: _tabController,
          indicatorColor: Theme.of(context).colorScheme.primary,
          labelColor: Theme.of(context).colorScheme.primary,
          unselectedLabelColor: Theme.of(
            context,
          ).textTheme.bodyMedium?.color?.withOpacity(0.6),
          tabs: const [
            Tab(text: 'Momentum'),
            Tab(text: 'NIFTY'),
            Tab(text: 'Futures'),
            Tab(text: 'Options'),
          ],
        ),
      ),
      body: Column(
        children: [
          // Date display
          if (_momentumData != null ||
              _niftyData != null ||
              _futuresTable != null ||
              _optionsData != null)
            Container(
              padding: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              color: Theme.of(context).cardColor,
              child: Row(
                children: [
                  Icon(
                    Icons.calendar_today,
                    size: 14,
                    color: Theme.of(
                      context,
                    ).textTheme.bodyMedium?.color?.withOpacity(0.6),
                  ),
                  SizedBox(width: 8),
                  Text(
                    _dataDate,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                      fontSize: 13,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  Spacer(),
                  Text(
                    'Auto-detected Market Day',
                    style: TextStyle(
                      color: Theme.of(
                        context,
                      ).textTheme.bodyMedium?.color?.withOpacity(0.4),
                      fontSize: 10,
                    ),
                  ),
                ],
              ),
            ),

          if (_error != null)
            Container(
              margin: EdgeInsets.all(16),
              padding: EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppTheme.errorColor.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Row(
                children: [
                  Icon(Icons.error_outline, color: AppTheme.errorColor, size: 20),
                  SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      _error!,
                      style: TextStyle(color: AppTheme.errorColor),
                    ),
                  ),
                ],
              ),
            ),

          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : TabBarView(
                    controller: _tabController,
                    children: [
                      _buildMomentumTab(),
                      _buildNiftyTab(),
                      _buildFuturesTab(),
                      _buildOptionsTab(),
                    ],
                  ),
          ),
        ],
      ),
    );
  }

  // -------------------------------------------------------------- NIFTY tab

  Widget _buildNiftyTab() {
    final data = _niftyData;
    if (data == null) {
      return _buildEmpty('No index data available');
    }

    return SingleChildScrollView(
      padding: EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _buildChipRow('Index', data.availableSymbols, _niftySymbol, (sym) {
            setState(() {
              _niftySymbol = sym;
              _niftyExpiry = ''; // expiries differ per index
            });
            _loadNiftyData();
          }),
          SizedBox(height: 16),
          _buildChipRow('Expiry', data.availableExpiries, _niftyExpiry, (exp) {
            setState(() => _niftyExpiry = exp);
            _loadNiftyData();
          }),
          SizedBox(height: 20),
          _buildChainSummary(data),
          SizedBox(height: 16),
          _buildOptionChain(data),
          if (data.futures.isNotEmpty) ...[
            SizedBox(height: 24),
            Text(
              '${data.symbol} Index Futures',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
            ),
            SizedBox(height: 8),
            ...data.futures.map(_buildContractCard),
          ],
        ],
      ),
    );
  }

  // ------------------------------------------------------------ Futures tab

  Widget _buildFuturesTab() {
    final data = _futuresTable;
    if (data == null) {
      return _buildEmpty('No futures data available');
    }

    return SingleChildScrollView(
      padding: EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              _buildFilterChip('Index (IDF)', _futuresSegment == 'index', () {
                if (_futuresSegment == 'index') return;
                setState(() {
                  _futuresSegment = 'index';
                  _futuresExpiry = '';
                  _futuresSymbol = '';
                });
                _loadFuturesData();
              }),
              SizedBox(width: 8),
              _buildFilterChip('Stock (STF)', _futuresSegment == 'stock', () {
                if (_futuresSegment == 'stock') return;
                setState(() {
                  _futuresSegment = 'stock';
                  _futuresExpiry = '';
                  _futuresSymbol = '';
                });
                _loadFuturesData();
              }),
            ],
          ),
          SizedBox(height: 16),
          _buildChipRow(
            'Expiry',
            ['', ...data.availableExpiries],
            _futuresExpiry,
            (exp) {
              setState(() => _futuresExpiry = exp);
              _loadFuturesData();
            },
            allLabel: 'All',
          ),
          SizedBox(height: 16),
          _buildChipRow(
            'Symbol',
            ['', ...data.availableSymbols],
            _futuresSymbol,
            (sym) {
              setState(() => _futuresSymbol = sym);
              _loadFuturesData();
            },
            allLabel: 'All',
          ),
          SizedBox(height: 20),
          if (data.rows.isEmpty)
            _buildEmpty('No contracts match these filters')
          else
            ...data.rows.map(_buildContractCard),
        ],
      ),
    );
  }

  // ------------------------------------------------------------ Options tab

  Widget _buildOptionsTab() {
    final data = _optionsData;
    if (data == null) {
      return _buildEmpty('No options data available');
    }

    return SingleChildScrollView(
      padding: EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _buildChipRow('Symbol', data.availableSymbols, _optionsSymbol, (sym) {
            setState(() {
              _optionsSymbol = sym;
              _optionsExpiry = '';
            });
            _loadOptionsData();
          }),
          SizedBox(height: 16),
          _buildChipRow('Expiry', data.availableExpiries, _optionsExpiry, (exp) {
            setState(() => _optionsExpiry = exp);
            _loadOptionsData();
          }),
          SizedBox(height: 20),
          _buildChainSummary(data),
          SizedBox(height: 16),
          _buildOptionChain(data),
        ],
      ),
    );
  }

  // ------------------------------------------------------- shared chain UI

  Widget _buildChainSummary(OptionChainData data) {
    final summary = data.summary;
    if (summary == null) return SizedBox.shrink();

    final pcr = summary.pcr ?? 0;
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        _buildStatTile('Spot', _fmt(data.underlyingPrice), null),
        _buildStatTile(
          'PCR (OI)',
          pcr.toStringAsFixed(2),
          pcr > 1 ? AppTheme.successColor : AppTheme.errorColor,
        ),
        _buildStatTile('Support', _fmt(summary.maxPeOiStrike, decimals: 0),
            AppTheme.successColor),
        _buildStatTile('Resistance', _fmt(summary.maxCeOiStrike, decimals: 0),
            AppTheme.errorColor),
        _buildStatTile('Call OI', _compact(summary.totalCeOi), null),
        _buildStatTile('Put OI', _compact(summary.totalPeOi), null),
      ],
    );
  }

  Widget _buildStatTile(String label, String value, Color? valueColor) {
    return Container(
      width: 104,
      padding: EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: Theme.of(context).cardTheme.color,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: Theme.of(context).colorScheme.onSurface.withOpacity(0.1),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label.toUpperCase(),
            style: TextStyle(
              fontSize: 9,
              letterSpacing: 0.6,
              fontWeight: FontWeight.w700,
              color: Theme.of(
                context,
              ).textTheme.bodyMedium?.color?.withOpacity(0.6),
            ),
          ),
          SizedBox(height: 4),
          Text(
            value,
            style: TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.w700,
              color: valueColor,
            ),
          ),
        ],
      ),
    );
  }

  /// CE | Strike | PE table, with an OI bar behind each open-interest cell.
  Widget _buildOptionChain(OptionChainData data) {
    if (data.chain.isEmpty) {
      return _buildEmpty('No option chain for this symbol and expiry');
    }

    final borderColor = Theme.of(context).colorScheme.onSurface.withOpacity(0.1);

    return Container(
      decoration: BoxDecoration(
        color: Theme.of(context).cardTheme.color,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: borderColor),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        children: [
          Padding(
            padding: EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            child: Row(
              children: [
                Text(
                  '${data.symbol} Option Chain',
                  style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
                ),
                Spacer(),
                Text(
                  '${data.expiry ?? ''} · ${data.chain.length} strikes',
                  style: TextStyle(
                    fontSize: 11,
                    color: Theme.of(
                      context,
                    ).textTheme.bodyMedium?.color?.withOpacity(0.6),
                  ),
                ),
              ],
            ),
          ),
          Container(
            padding: EdgeInsets.symmetric(horizontal: 8, vertical: 6),
            color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.04),
            child: Row(
              children: [
                Expanded(
                  flex: 3,
                  child: Text(
                    'CALLS  OI / Chg',
                    style: TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                      color: AppTheme.successColor,
                    ),
                  ),
                ),
                Expanded(
                  flex: 2,
                  child: Text(
                    'STRIKE',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 10, fontWeight: FontWeight.w700),
                  ),
                ),
                Expanded(
                  flex: 3,
                  child: Text(
                    'Chg / OI  PUTS',
                    textAlign: TextAlign.right,
                    style: TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                      color: AppTheme.errorColor,
                    ),
                  ),
                ),
              ],
            ),
          ),
          ...data.chain.map((row) => _buildChainRow(row, data)),
        ],
      ),
    );
  }

  Widget _buildChainRow(OptionChainRow row, OptionChainData data) {
    final spot = data.underlyingPrice;
    final isAtm = data.summary?.atmStrike == row.strike;
    final callItm = spot != null && row.strike < spot;
    final putItm = spot != null && row.strike > spot;

    return Container(
      decoration: BoxDecoration(
        color: isAtm
            ? Theme.of(context).colorScheme.primary.withValues(alpha: 0.08)
            : null,
        border: Border(
          top: BorderSide(
            color: Theme.of(context).colorScheme.onSurface.withOpacity(0.06),
          ),
        ),
      ),
      padding: EdgeInsets.symmetric(horizontal: 8, vertical: 8),
      child: Row(
        children: [
          Expanded(
            flex: 3,
            child: _buildChainCell(
              oi: row.ceOi,
              oiChange: row.ceOiChange,
              ltp: row.ceLtp,
              barColor: AppTheme.successColor,
              itm: callItm,
              alignRight: false,
            ),
          ),
          Expanded(
            flex: 2,
            child: Text(
              _fmt(row.strike, decimals: 0),
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w700,
                color: isAtm ? Theme.of(context).colorScheme.primary : null,
              ),
            ),
          ),
          Expanded(
            flex: 3,
            child: _buildChainCell(
              oi: row.peOi,
              oiChange: row.peOiChange,
              ltp: row.peLtp,
              barColor: AppTheme.errorColor,
              itm: putItm,
              alignRight: true,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildChainCell({
    required double? oi,
    required double? oiChange,
    required double? ltp,
    required Color barColor,
    required bool itm,
    required bool alignRight,
  }) {
    final barFraction = ((oi ?? 0) / _maxChainOi).clamp(0.0, 1.0);
    final changeColor = (oiChange ?? 0) >= 0
        ? AppTheme.successColor
        : AppTheme.errorColor;

    final texts = Column(
      crossAxisAlignment: alignRight
          ? CrossAxisAlignment.end
          : CrossAxisAlignment.start,
      children: [
        Text(
          _compact(oi),
          style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
        ),
        SizedBox(height: 2),
        Text(
          'LTP ${_fmt(ltp)}  ${(oiChange ?? 0) > 0 ? '+' : ''}${_compact(oiChange)}',
          style: TextStyle(fontSize: 10, color: changeColor),
        ),
      ],
    );

    return Stack(
      children: [
        Positioned.fill(
          child: Align(
            alignment: alignRight ? Alignment.centerLeft : Alignment.centerRight,
            child: FractionallySizedBox(
              widthFactor: barFraction,
              child: Container(
                decoration: BoxDecoration(
                  color: barColor.withValues(alpha: itm ? 0.22 : 0.14),
                  borderRadius: BorderRadius.circular(3),
                ),
              ),
            ),
          ),
        ),
        Padding(padding: EdgeInsets.symmetric(horizontal: 4), child: texts),
      ],
    );
  }

  /// A futures contract row: price, % change, open interest and % OI change.
  Widget _buildContractCard(Map<String, dynamic> item) {
    final name = (item['FinInstrmNm'] ?? item['TckrSymb'] ?? '').toString();
    final priceChange = (item['pct_price_change'] as num?)?.toDouble() ?? 0;
    final oiChange = (item['pct_oi_change'] as num?)?.toDouble() ?? 0;

    return Container(
      margin: EdgeInsets.only(bottom: 8),
      padding: EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Theme.of(context).cardTheme.color,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: Theme.of(context).colorScheme.onSurface.withOpacity(0.1),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  name,
                  style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
                ),
              ),
              Text(
                (item['XpryDt'] ?? '').toString(),
                style: TextStyle(
                  fontSize: 11,
                  color: Theme.of(
                    context,
                  ).textTheme.bodyMedium?.color?.withOpacity(0.6),
                ),
              ),
            ],
          ),
          SizedBox(height: 10),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              _buildMiniStat('Close', _fmt(item['ClsPric'])),
              _buildMiniStat(
                '% Chg',
                '${priceChange > 0 ? '+' : ''}${priceChange.toStringAsFixed(2)}%',
                color: priceChange >= 0
                    ? AppTheme.successColor
                    : AppTheme.errorColor,
              ),
              _buildMiniStat('OI', _compact(item['OpnIntrst'])),
              _buildMiniStat(
                '% Chg OI',
                '${oiChange > 0 ? '+' : ''}${oiChange.toStringAsFixed(2)}%',
                color: oiChange >= 0
                    ? AppTheme.successColor
                    : AppTheme.errorColor,
              ),
            ],
          ),
        ],
      ),
    );
  }

  // ---------------------------------------------------------------- helpers

  /// Horizontally scrollable selector. An empty-string option renders as [allLabel].
  Widget _buildChipRow(
    String label,
    List<String> values,
    String selected,
    void Function(String) onSelect, {
    String? allLabel,
  }) {
    if (values.isEmpty) return SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: TextStyle(
            fontSize: 13,
            color: Theme.of(
              context,
            ).textTheme.bodyMedium?.color?.withOpacity(0.6),
          ),
        ),
        SizedBox(height: 8),
        SizedBox(
          height: 36,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            itemCount: values.length,
            separatorBuilder: (_, _) => SizedBox(width: 8),
            itemBuilder: (context, index) {
              final value = values[index];
              final isSelected = value == selected;
              return GestureDetector(
                onTap: () => onSelect(value),
                child: Container(
                  padding: EdgeInsets.symmetric(horizontal: 14),
                  decoration: BoxDecoration(
                    color: isSelected
                        ? Theme.of(context).colorScheme.primary
                        : Theme.of(context).cardTheme.color,
                    borderRadius: BorderRadius.circular(18),
                    border: Border.all(
                      color: isSelected
                          ? Theme.of(context).colorScheme.primary
                          : Theme.of(
                              context,
                            ).colorScheme.onSurface.withOpacity(0.12),
                    ),
                  ),
                  alignment: Alignment.center,
                  child: Text(
                    value.isEmpty ? (allLabel ?? 'All') : value,
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: isSelected
                          ? FontWeight.w600
                          : FontWeight.normal,
                    ),
                  ),
                ),
              );
            },
          ),
        ),
      ],
    );
  }

  Widget _buildEmpty(String message) {
    return Center(
      child: Padding(
        padding: EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.info_outline,
              size: 40,
              color: Theme.of(
                context,
              ).textTheme.bodyMedium?.color?.withOpacity(0.6),
            ),
            SizedBox(height: 12),
            Text(
              message,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Theme.of(
                  context,
                ).textTheme.bodyMedium?.color?.withOpacity(0.6),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildFilterChip(String label, bool isActive, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: BoxDecoration(
          color: isActive
              ? Theme.of(context).colorScheme.primary
              : Theme.of(context).cardTheme.color,
          borderRadius: BorderRadius.circular(20),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontWeight: isActive ? FontWeight.w600 : FontWeight.normal,
            fontSize: 13,
          ),
        ),
      ),
    );
  }

  Widget _buildMiniStat(String label, String value, {Color? color}) {
    return Column(
      children: [
        Text(
          label,
          style: TextStyle(
            fontSize: 10,
            color: Theme.of(
              context,
            ).textTheme.bodyMedium?.color?.withOpacity(0.6),
          ),
        ),
        SizedBox(height: 2),
        Text(
          value,
          style: TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.w600,
            color: color,
          ),
        ),
      ],
    );
  }

  String _fmt(dynamic value, {int decimals = 2}) {
    if (value == null) return '-';
    final n = value is num ? value.toDouble() : double.tryParse('$value');
    return n == null ? '-' : n.toStringAsFixed(decimals);
  }

  /// 12,50,000 -> 12.5L, so open interest fits in a phone-width cell.
  String _compact(dynamic value) {
    if (value == null) return '-';
    final n = value is num ? value.toDouble() : double.tryParse('$value');
    if (n == null) return '-';
    final sign = n < 0 ? '-' : '';
    final abs = n.abs();
    if (abs >= 10000000) return '$sign${(abs / 10000000).toStringAsFixed(2)}Cr';
    if (abs >= 100000) return '$sign${(abs / 100000).toStringAsFixed(2)}L';
    if (abs >= 1000) return '$sign${(abs / 1000).toStringAsFixed(1)}K';
    return '$sign${abs.toStringAsFixed(0)}';
  }

  // --------------------------------------------------------- Momentum tab

  Widget _buildMomentumTab() {
    return SingleChildScrollView(
      padding: EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (_momentumExpiries.isNotEmpty) ...[
            _buildChipRow('Expiry Contract', _momentumExpiries, _momentumExpiry, (
              exp,
            ) {
              setState(() => _momentumExpiry = exp);
              _loadMomentumData();
            }),
            SizedBox(height: 20),
          ],

          if (_momentumData != null && _top10.isEmpty && _bottom10.isEmpty)
            _buildEmpty('No momentum data available'),

          if (_top10.isNotEmpty) ...[
            Text(
              'Long Buildup',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
                color: AppTheme.successColor,
              ),
            ),
            SizedBox(height: 12),
            ..._top10.map(
              (item) => _buildMomentumCard(item as Map<String, dynamic>, true),
            ),
          ],
          if (_bottom10.isNotEmpty) ...[
            SizedBox(height: 24),
            Text(
              'Short Buildup',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
                color: AppTheme.errorColor,
              ),
            ),
            SizedBox(height: 12),
            ..._bottom10.map(
              (item) => _buildMomentumCard(item as Map<String, dynamic>, false),
            ),
          ],
          if (_shortCovering.isNotEmpty) ...[
            SizedBox(height: 24),
            Text(
              'Short Covering',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
                color: AppTheme.successColor,
              ),
            ),
            SizedBox(height: 12),
            ..._shortCovering.map(
              (item) => _buildMomentumCard(item as Map<String, dynamic>, true),
            ),
          ],
          if (_longUnwinding.isNotEmpty) ...[
            SizedBox(height: 24),
            Text(
              'Long Unwinding',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
                color: AppTheme.errorColor,
              ),
            ),
            SizedBox(height: 12),
            ..._longUnwinding.map(
              (item) => _buildMomentumCard(item as Map<String, dynamic>, false),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildMomentumCard(Map<String, dynamic> item, bool isLong) {
    final symbol = (item['TckrSymb'] ?? '').toString();
    final price = _fmt(item['ClsPric'] ?? item['LastPric']);
    final priceChange = (item['pct_price_change'] as num?)?.toDouble() ?? 0.0;
    final oiChange = (item['pct_oi_change'] as num?)?.toDouble() ?? 0.0;

    final isPriceUp = priceChange > 0;
    final priceColor = isPriceUp ? AppTheme.successColor : AppTheme.errorColor;
    final iconColor = isLong ? AppTheme.successColor : AppTheme.errorColor;

    return Container(
      margin: EdgeInsets.only(bottom: 8),
      padding: EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: Theme.of(context).cardTheme.color,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: Theme.of(context).colorScheme.onSurface.withOpacity(0.1),
        ),
      ),
      child: Column(
        children: [
          Row(
            children: [
              Container(
                width: 32,
                height: 32,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: iconColor,
                ),
                child: Center(
                  child: Text(
                    symbol.isNotEmpty ? symbol[0] : '',
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.bold,
                      color: Theme.of(context).colorScheme.onSurface,
                    ),
                  ),
                ),
              ),
              SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      symbol,
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.bold,
                        color: Theme.of(context).colorScheme.onSurface,
                      ),
                    ),
                    SizedBox(height: 2),
                    Row(
                      children: [
                        Text(
                          price,
                          style: TextStyle(
                            fontSize: 12,
                            color: Theme.of(
                              context,
                            ).colorScheme.onSurface.withOpacity(0.7),
                          ),
                        ),
                        SizedBox(width: 6),
                        Text(
                          '(${isPriceUp ? '+' : ''}${priceChange.toStringAsFixed(2)}%)',
                          style: TextStyle(fontSize: 12, color: priceColor),
                        ),
                      ],
                    ),
                    SizedBox(height: 2),
                    Text(
                      'OI ${_compact(item['OpnIntrst'])}',
                      style: TextStyle(
                        fontSize: 11,
                        color: Theme.of(
                          context,
                        ).colorScheme.onSurface.withOpacity(0.6),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          SizedBox(height: 10),
          // Progress bar native implementation
          Container(
            height: 14,
            width: double.infinity,
            decoration: BoxDecoration(
              color: Theme.of(
                context,
              ).colorScheme.onSurface.withValues(alpha: 0.05),
              borderRadius: BorderRadius.circular(3),
            ),
            child: Row(
              children: [
                Expanded(
                  flex: oiChange.abs().toInt().clamp(5, 100),
                  child: Container(
                    decoration: BoxDecoration(
                      color: oiChange > 0
                          ? AppTheme.successColor
                          : AppTheme.errorColor,
                      borderRadius: BorderRadius.circular(3),
                    ),
                    alignment: Alignment.centerRight,
                    padding: EdgeInsets.symmetric(horizontal: 6),
                    child: Text(
                      '${oiChange > 0 ? '+' : ''}${oiChange.toStringAsFixed(2)}%',
                      style: TextStyle(
                        fontSize: 9,
                        fontWeight: FontWeight.bold,
                        color: Theme.of(context).colorScheme.onSurface,
                      ),
                    ),
                  ),
                ),
                Expanded(
                  flex: 100 - oiChange.abs().toInt().clamp(5, 100),
                  child: SizedBox(),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
