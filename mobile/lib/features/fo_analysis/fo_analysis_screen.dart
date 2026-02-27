import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../../config/theme.dart';
import '../../core/models/fo_data.dart';
import '../../core/services/fo_service.dart';

class FOAnalysisScreen extends StatefulWidget {
  const FOAnalysisScreen({super.key});

  @override
  State<FOAnalysisScreen> createState() => _FOAnalysisScreenState();
}

class _FOAnalysisScreenState extends State<FOAnalysisScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;
  DateTime _selectedDate = DateTime.now();

  bool _loading = false;
  String? _error;

  // NIFTY tab
  NiftyData? _niftyData;
  List<String> _uniqueSymbols = [];
  List<String> _uniqueExpiries = [];
  String _selectedSymbol = 'NIFTY';
  String _selectedExpiry = '';
  List<Map<String, dynamic>> _filteredFutures = [];
  List<Map<String, dynamic>> _filteredOptions = [];

  // Futures tab
  String _futuresSymbol = 'NIFTY';
  List<Map<String, dynamic>> _futuresData = [];

  // Options tab
  String _optionsSymbol = 'NIFTY';
  String _optionType = '';
  List<Map<String, dynamic>> _optionsData = [];

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
    _tabController.addListener(() {
      if (!_tabController.indexIsChanging) {
        _onTabChange(_tabController.index);
      }
    });
    _loadNiftyData();
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  String _formatDate(DateTime date) => DateFormat('yyyy-MM-dd').format(date);

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _selectedDate,
      firstDate: DateTime(2020),
      lastDate: DateTime.now(),
      builder: (context, child) {
        return Theme(
          data: AppTheme.darkTheme.copyWith(
            colorScheme: ColorScheme.dark(
              primary: AppTheme.primaryColor,
              surface: AppTheme.cardColor,
            ),
          ),
          child: child!,
        );
      },
    );
    if (picked != null) {
      setState(() => _selectedDate = picked);
      _onTabChange(_tabController.index);
    }
  }

  void _onTabChange(int index) {
    setState(() => _error = null);
    switch (index) {
      case 0:
        if (_niftyData == null) _loadNiftyData();
        break;
      case 1:
        _loadFuturesData();
        break;
      case 2:
        _loadOptionsData();
        break;
    }
  }

  Future<void> _loadNiftyData() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await FOService.getNiftyData(_formatDate(_selectedDate));
      setState(() {
        _niftyData = data;
        _processNiftyFilters(data);
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString().replaceAll('Exception: ', '');
        _loading = false;
      });
    }
  }

  void _processNiftyFilters(NiftyData data) {
    final allItems = [...data.futures, ...data.options];
    if (allItems.isEmpty) {
      _uniqueSymbols = [];
      _uniqueExpiries = [];
      _filteredFutures = [];
      _filteredOptions = [];
      return;
    }

    _uniqueSymbols =
        allItems
            .map(
              (item) =>
                  (item['TckrSymb'] ?? item['UndrlygVal'] ?? '').toString(),
            )
            .where((s) => s.isNotEmpty)
            .toSet()
            .toList()
          ..sort();

    if (!_uniqueSymbols.contains(_selectedSymbol)) {
      _selectedSymbol = _uniqueSymbols.contains('NIFTY')
          ? 'NIFTY'
          : (_uniqueSymbols.isNotEmpty ? _uniqueSymbols.first : '');
    }

    _updateExpiries();
    _applyFilters();
  }

  void _updateExpiries() {
    if (_niftyData == null) return;
    final allItems = [..._niftyData!.futures, ..._niftyData!.options];
    final symbolItems = allItems.where(
      (item) =>
          item['TckrSymb'] == _selectedSymbol ||
          item['UndrlygVal'] == _selectedSymbol,
    );

    _uniqueExpiries =
        symbolItems
            .map((item) => (item['XpryDt'] ?? '').toString())
            .where((s) => s.isNotEmpty)
            .toSet()
            .toList()
          ..sort();

    if (!_uniqueExpiries.contains(_selectedExpiry) &&
        _uniqueExpiries.isNotEmpty) {
      _selectedExpiry = _uniqueExpiries.first;
    }
  }

  void _applyFilters() {
    if (_niftyData == null) return;
    _filteredFutures = _niftyData!.futures.where((item) {
      final matchSym =
          item['TckrSymb'] == _selectedSymbol ||
          item['UndrlygVal'] == _selectedSymbol;
      final matchExp = item['XpryDt'] == _selectedExpiry;
      return matchSym && matchExp;
    }).toList();

    _filteredOptions = _niftyData!.options.where((item) {
      final matchSym =
          item['TckrSymb'] == _selectedSymbol ||
          item['UndrlygVal'] == _selectedSymbol;
      final matchExp = item['XpryDt'] == _selectedExpiry;
      return matchSym && matchExp;
    }).toList();
  }

  Future<void> _loadFuturesData() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await FOService.getFuturesData(
        _futuresSymbol,
        _formatDate(_selectedDate),
      );
      setState(() {
        _futuresData = data.data;
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString().replaceAll('Exception: ', '');
        _loading = false;
      });
    }
  }

  Future<void> _loadOptionsData() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await FOService.getOptionsData(
        _optionsSymbol,
        _formatDate(_selectedDate),
        _optionType.isNotEmpty ? _optionType : null,
      );
      setState(() {
        _optionsData = data.data;
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString().replaceAll('Exception: ', '');
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('F&O Analysis'),
        actions: [
          IconButton(
            icon: const Icon(Icons.calendar_today, size: 20),
            onPressed: _pickDate,
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => _onTabChange(_tabController.index),
          ),
        ],
        bottom: TabBar(
          controller: _tabController,
          indicatorColor: AppTheme.primaryColor,
          labelColor: AppTheme.primaryColor,
          unselectedLabelColor: AppTheme.textSecondary,
          tabs: const [
            Tab(text: 'NIFTY'),
            Tab(text: 'Futures'),
            Tab(text: 'Options'),
          ],
        ),
      ),
      body: Column(
        children: [
          // Date display
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            color: AppTheme.cardColor,
            child: Row(
              children: [
                Icon(
                  Icons.calendar_today,
                  size: 14,
                  color: AppTheme.textSecondary,
                ),
                const SizedBox(width: 8),
                Text(
                  DateFormat('dd MMM yyyy').format(_selectedDate),
                  style: TextStyle(color: AppTheme.textSecondary, fontSize: 13),
                ),
              ],
            ),
          ),

          if (_error != null)
            Container(
              margin: const EdgeInsets.all(16),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppTheme.errorColor.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Row(
                children: [
                  const Icon(
                    Icons.error_outline,
                    color: AppTheme.errorColor,
                    size: 20,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      _error!,
                      style: const TextStyle(color: AppTheme.errorColor),
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
                      _buildNiftyTab(),
                      _buildDataTab(_futuresData, 'futures'),
                      _buildOptionsTab(),
                    ],
                  ),
          ),
        ],
      ),
    );
  }

  Widget _buildNiftyTab() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Symbol filter
          if (_uniqueSymbols.isNotEmpty) ...[
            const Text(
              'Symbol',
              style: TextStyle(fontSize: 13, color: AppTheme.textSecondary),
            ),
            const SizedBox(height: 8),
            SizedBox(
              height: 36,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: _uniqueSymbols.length,
                separatorBuilder: (_, __) => const SizedBox(width: 8),
                itemBuilder: (context, index) {
                  final sym = _uniqueSymbols[index];
                  final isSelected = sym == _selectedSymbol;
                  return GestureDetector(
                    onTap: () {
                      setState(() {
                        _selectedSymbol = sym;
                        _updateExpiries();
                        _applyFilters();
                      });
                    },
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 16),
                      decoration: BoxDecoration(
                        color: isSelected
                            ? AppTheme.primaryColor
                            : AppTheme.cardColor,
                        borderRadius: BorderRadius.circular(18),
                        border: Border.all(
                          color: isSelected
                              ? AppTheme.primaryColor
                              : Colors.white12,
                        ),
                      ),
                      alignment: Alignment.center,
                      child: Text(
                        sym,
                        style: TextStyle(
                          fontSize: 13,
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
            const SizedBox(height: 16),
          ],

          // Expiry filter
          if (_uniqueExpiries.isNotEmpty) ...[
            const Text(
              'Expiry',
              style: TextStyle(fontSize: 13, color: AppTheme.textSecondary),
            ),
            const SizedBox(height: 8),
            SizedBox(
              height: 36,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: _uniqueExpiries.length,
                separatorBuilder: (_, __) => const SizedBox(width: 8),
                itemBuilder: (context, index) {
                  final exp = _uniqueExpiries[index];
                  final isSelected = exp == _selectedExpiry;
                  return GestureDetector(
                    onTap: () {
                      setState(() {
                        _selectedExpiry = exp;
                        _applyFilters();
                      });
                    },
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 14),
                      decoration: BoxDecoration(
                        color: isSelected
                            ? AppTheme.accentColor
                            : AppTheme.cardColor,
                        borderRadius: BorderRadius.circular(18),
                        border: Border.all(
                          color: isSelected
                              ? AppTheme.accentColor
                              : Colors.white12,
                        ),
                      ),
                      alignment: Alignment.center,
                      child: Text(
                        exp,
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
            const SizedBox(height: 20),
          ],

          // Futures section
          if (_filteredFutures.isNotEmpty) ...[
            Text(
              'Futures (${_filteredFutures.length})',
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 8),
            ..._filteredFutures.map((item) => _buildFOCard(item)),
            const SizedBox(height: 20),
          ],

          // Options section
          if (_filteredOptions.isNotEmpty) ...[
            Text(
              'Options (${_filteredOptions.length})',
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 8),
            ..._filteredOptions.map((item) => _buildFOCard(item)),
          ],

          if (_filteredFutures.isEmpty && _filteredOptions.isEmpty)
            Center(
              child: Padding(
                padding: const EdgeInsets.all(32),
                child: Column(
                  children: [
                    Icon(
                      Icons.info_outline,
                      size: 48,
                      color: AppTheme.textSecondary,
                    ),
                    const SizedBox(height: 12),
                    Text(
                      'No data available',
                      style: TextStyle(color: AppTheme.textSecondary),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildOptionsTab() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Option type filter
          Row(
            children: [
              _buildFilterChip('All', _optionType == '', () {
                setState(() => _optionType = '');
                _loadOptionsData();
              }),
              const SizedBox(width: 8),
              _buildFilterChip('CE', _optionType == 'CE', () {
                setState(() => _optionType = 'CE');
                _loadOptionsData();
              }),
              const SizedBox(width: 8),
              _buildFilterChip('PE', _optionType == 'PE', () {
                setState(() => _optionType = 'PE');
                _loadOptionsData();
              }),
            ],
          ),
          const SizedBox(height: 16),
          ..._optionsData.map((item) => _buildFOCard(item)),
          if (_optionsData.isEmpty)
            Center(
              child: Padding(
                padding: const EdgeInsets.all(32),
                child: Text(
                  'No options data',
                  style: TextStyle(color: AppTheme.textSecondary),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildFilterChip(String label, bool isActive, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: BoxDecoration(
          color: isActive ? AppTheme.primaryColor : AppTheme.cardColor,
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

  Widget _buildDataTab(List<Map<String, dynamic>> data, String type) {
    return data.isEmpty
        ? Center(
            child: Text(
              'No $type data',
              style: TextStyle(color: AppTheme.textSecondary),
            ),
          )
        : ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: data.length,
            itemBuilder: (context, index) => _buildFOCard(data[index]),
          );
  }

  Widget _buildFOCard(Map<String, dynamic> item) {
    final symbol = item['TckrSymb'] ?? item['UndrlygVal'] ?? '';
    final close = item['ClsPric'] ?? item['LastPric'] ?? '';
    final open = item['OpnPric'] ?? '';
    final high = item['HghPric'] ?? '';
    final low = item['LwPric'] ?? '';
    final volume = item['TtlTrdVol'] ?? item['TdTradVol'] ?? '';

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppTheme.cardColor,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '$symbol',
            style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
          ),
          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              _buildMiniStat('Open', '$open'),
              _buildMiniStat('High', '$high'),
              _buildMiniStat('Low', '$low'),
              _buildMiniStat('Close', '$close'),
            ],
          ),
          if (volume.toString().isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
              'Vol: $volume',
              style: TextStyle(fontSize: 11, color: AppTheme.textSecondary),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildMiniStat(String label, String value) {
    return Column(
      children: [
        Text(
          label,
          style: TextStyle(fontSize: 10, color: AppTheme.textSecondary),
        ),
        const SizedBox(height: 2),
        Text(
          value,
          style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
        ),
      ],
    );
  }
}
