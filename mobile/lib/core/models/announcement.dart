class NSEAnnouncement {
  final String symbol;
  final String companyName;
  final String subject;
  final String broadcastDate;
  final String attachmentLink;
  final String category;

  NSEAnnouncement({
    required this.symbol,
    required this.companyName,
    required this.subject,
    required this.broadcastDate,
    required this.attachmentLink,
    required this.category,
  });

  factory NSEAnnouncement.fromJson(Map<String, dynamic> json) {
    return NSEAnnouncement(
      symbol: json['symbol'] ?? '',
      companyName: json['company_name'] ?? '',
      subject: json['subject'] ?? '',
      broadcastDate: json['broadcast_date'] ?? '',
      attachmentLink: json['attachment_link'] ?? '',
      category: json['category'] ?? '',
    );
  }
}

class BSEAnnouncement {
  final String scripCode;
  final String companyName;
  final String subject;
  final String newsDate;
  final String category;
  final String? attachmentUrl;
  final String newsId;

  BSEAnnouncement({
    required this.scripCode,
    required this.companyName,
    required this.subject,
    required this.newsDate,
    required this.category,
    this.attachmentUrl,
    required this.newsId,
  });

  factory BSEAnnouncement.fromJson(Map<String, dynamic> json) {
    return BSEAnnouncement(
      scripCode: json['scrip_code']?.toString() ?? '',
      companyName: json['company_name'] ?? '',
      subject: json['subject'] ?? '',
      newsDate: json['news_date'] ?? '',
      category: json['category'] ?? '',
      attachmentUrl: json['attachment_url'],
      newsId: json['news_id']?.toString() ?? '',
    );
  }
}
