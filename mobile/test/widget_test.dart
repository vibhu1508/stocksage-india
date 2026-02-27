import 'package:flutter_test/flutter_test.dart';
import 'package:stocksage_india/main.dart';

void main() {
  testWidgets('App loads', (WidgetTester tester) async {
    await tester.pumpWidget(const StockSageApp());
    // App should show a loading indicator while initializing
    expect(find.byType(StockSageApp), findsOneWidget);
  });
}
