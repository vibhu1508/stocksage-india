import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../../config/theme.dart';
import '../../core/models/stock.dart';
import '../../core/services/stock_service.dart';

class StockComparisonScreen extends StatefulWidget {
  const StockComparisonScreen({super.key});

  @override
  State<StockComparisonScreen> createState() => _StockComparisonScreenState();
}

class _StockComparisonScreenState extends State<StockComparisonScreen> {
  final _symbolController = TextEditingController();
  DateTime _date1 = DateTime.now().subtract(const Duration(days: 1));
  DateTime _date2 = DateTime.now();

  bool _loading = false;
  String? _error;
  StockComparison? _comparison;
  String _activeTab = 'all';

  // Autocomplete
  List<SymbolSearchResult> _suggestions = [];
  bool _showSuggestions = false;

  // Table search
  final _tableSearchController = TextEditingController();

  @override
  void dispose() {
    _symbolController.dispose();
    _tableSearchController.dispose();
    super.dispose();
  }

  String _formatDate(DateTime date) => DateFormat('yyyy-MM-dd').format(date);

  Future<void> _pickDate(bool isDate1) async {
    final picked = await showDatePicker(
      context: context,
      initialDate: isDate1 ? _date1 : _date2,
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
      setState(() {
        if (isDate1) {
          _date1 = picked;
        } else {
          _date2 = picked;
        }
      });
    }
  }

  Future<void> _searchSymbols(String query) async {
    if (query.length < 1) {
      setState(() => _showSuggestions = false);
      return;
    }
    // Get last part after comma
    final parts = query.split(',');
    final lastPart = parts.last.trim();
    if (lastPart.isEmpty) {
      setState(() => _showSuggestions = false);
      return;
    }

    try {
      final results = await StockService.searchSymbols(lastPart, 8);
      setState(() {
        _suggestions = results;
        _showSuggestions = results.isNotEmpty;
      });
    } catch (_) {}
  }

  void _selectSuggestion(SymbolSearchResult suggestion) {
    final parts = _symbolController.text
        .split(',')
        .map((s) => s.trim())
        .where((s) => s.isNotEmpty)
        .toList();
    if (parts.isNotEmpty) {
      parts[parts.length - 1] = suggestion.symbol;
    } else {
      parts.add(suggestion.symbol);
    }
    _symbolController.text = parts.join(', ');
    setState(() => _showSuggestions = false);
  }

  Future<void> _compareStocks() async {
    setState(() {
      _loading = true;
      _error = null;
      _comparison = null;
    });

    try {
      final comparison = await StockService.compareStocks(
        _formatDate(_date1),
        _formatDate(_date2),
        _symbolController.text.isNotEmpty ? _symbolController.text : null,
      );
      setState(() {
        _comparison = comparison;
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString().replaceAll('Exception: ', '');
        _loading = false;
      });
    }
  }

  List<ComparisonItem> get _displayedData {
    if (_comparison == null) return [];
    List<ComparisonItem> data;
    switch (_activeTab) {
      case 'gainers':
        data = _comparison!.gainers;
        break;
      case 'losers':
        data = _comparison!.losers;
        break;
      default:
        data = _comparison!.data;
    }

    // Apply table search filter
    final query = _tableSearchController.text.trim().toUpperCase();
    if (query.isNotEmpty) {
      data = data
          .where((item) => item.symbol.toUpperCase().contains(query))
          .toList();
    }
    return data;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Stock Comparison')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Date pickers
            Row(
              children: [
                Expanded(
                  child: _buildDateCard(
                    'Date 1',
                    _date1,
                    () => _pickDate(true),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _buildDateCard(
                    'Date 2',
                    _date2,
                    () => _pickDate(false),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),

            // Symbol input with autocomplete
            Stack(
              clipBehavior: Clip.none,
              children: [
                TextField(
                  controller: _symbolController,
                  decoration: InputDecoration(
                    hintText: 'Enter symbols (e.g., RELIANCE, TCS)',
                    prefixIcon: const Icon(
                      Icons.search,
                      color: AppTheme.textSecondary,
                    ),
                    suffixIcon: _symbolController.text.isNotEmpty
                        ? IconButton(
                            icon: const Icon(Icons.clear, size: 20),
                            onPressed: () {
                              _symbolController.clear();
                              setState(() => _showSuggestions = false);
                            },
                          )
                        : null,
                  ),
                  onChanged: _searchSymbols,
                  onTap: () => _searchSymbols(_symbolController.text),
                ),
                if (_showSuggestions)
                  Positioned(
                    top: 60,
                    left: 0,
                    right: 0,
                    child: Material(
                      color: AppTheme.cardColor,
                      elevation: 8,
                      borderRadius: BorderRadius.circular(12),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: _suggestions.map((s) {
                          return ListTile(
                            dense: true,
                            title: Text(
                              s.symbol,
                              style: const TextStyle(
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            subtitle: Text(
                              s.name,
                              style: TextStyle(
                                color: AppTheme.textSecondary,
                                fontSize: 12,
                              ),
                            ),
                            onTap: () => _selectSuggestion(s),
                          );
                        }).toList(),
                      ),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 16),

            // Compare button
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                onPressed: _loading ? null : _compareStocks,
                icon: _loading
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Icon(Icons.compare_arrows),
                label: Text(_loading ? 'Comparing...' : 'Compare Stocks'),
              ),
            ),
            const SizedBox(height: 20),

            // Error
            if (_error != null)
              Container(
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

            // Results
            if (_comparison != null) ...[
              // Tab bar
              Row(
                children: [
                  _buildTab('All', 'all', _comparison!.data.length),
                  const SizedBox(width: 8),
                  _buildTab('Gainers', 'gainers', _comparison!.gainers.length),
                  const SizedBox(width: 8),
                  _buildTab('Losers', 'losers', _comparison!.losers.length),
                ],
              ),
              const SizedBox(height: 12),

              // Search in table
              if (_activeTab == 'all')
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: TextField(
                    controller: _tableSearchController,
                    decoration: const InputDecoration(
                      hintText: 'Search symbol...',
                      prefixIcon: Icon(Icons.search, size: 20),
                      isDense: true,
                    ),
                    onChanged: (_) => setState(() {}),
                  ),
                ),

              // Data cards
              ..._displayedData.map((item) => _buildStockCard(item)),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildDateCard(String label, DateTime date, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: AppTheme.cardColor,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: Colors.white12),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label,
              style: TextStyle(fontSize: 12, color: AppTheme.textSecondary),
            ),
            const SizedBox(height: 4),
            Row(
              children: [
                const Icon(
                  Icons.calendar_today,
                  size: 16,
                  color: AppTheme.primaryColor,
                ),
                const SizedBox(width: 8),
                Text(
                  DateFormat('dd MMM yyyy').format(date),
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTab(String label, String value, int count) {
    final isActive = _activeTab == value;
    return Expanded(
      child: GestureDetector(
        onTap: () => setState(() => _activeTab = value),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 10),
          decoration: BoxDecoration(
            color: isActive ? AppTheme.primaryColor : AppTheme.cardColor,
            borderRadius: BorderRadius.circular(10),
          ),
          child: Center(
            child: Text(
              '$label ($count)',
              style: TextStyle(
                fontSize: 13,
                fontWeight: isActive ? FontWeight.w600 : FontWeight.normal,
                color: isActive ? Colors.white : AppTheme.textSecondary,
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildStockCard(ComparisonItem item) {
    final isPositive = item.pctChange > 0;
    final changeColor = isPositive
        ? AppTheme.successColor
        : AppTheme.errorColor;

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppTheme.cardColor,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          Expanded(
            flex: 3,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  item.symbol,
                  style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 15,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  '₹${item.oldPrice.toStringAsFixed(2)} → ₹${item.newPrice.toStringAsFixed(2)}',
                  style: TextStyle(fontSize: 12, color: AppTheme.textSecondary),
                ),
              ],
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
              color: changeColor.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              '${isPositive ? '+' : ''}${item.pctChange.toStringAsFixed(2)}%',
              style: TextStyle(
                color: changeColor,
                fontWeight: FontWeight.w700,
                fontSize: 14,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
