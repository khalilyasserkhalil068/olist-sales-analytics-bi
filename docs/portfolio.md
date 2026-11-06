# Portfolio and interview material

Use the following descriptions with the report previews and documented evidence. They describe completed local work. No deployment, realized uplift or production adoption is claimed.

## Repository description

End-to-end Olist sales analytics with Python, SQL Server and Power BI: a validated warehouse, five interactive dashboards, customer/RFM and cohort analysis, and independent KPI reconciliation.

## CV — English

**Sales Analytics & Business Intelligence | Python, SQL Server, Power BI**

- Built an analytics workflow from nine Olist CSVs through typed cleaning and a SQL Server warehouse to five native Power BI dashboard pages.
- Modeled separate order, item, payment and review grains; implemented 58 DAX measures with explicit eligibility and date/geography roles.
- Reconciled SQL/Python results through 3,948 assertions and validated the reopened report through 86 DAX cases and 39 page-query batches.
- Analyzed R$13.22M in eligible merchandise, 93,358 purchasing identities, delivery performance, RFM segments and monthly cohort retention.

## السيرة الذاتية — العربية

**تحليلات المبيعات وذكاء الأعمال | Python، SQL Server، Power BI**

- طوّرت مسارًا تحليليًا يبدأ من تسعة ملفات Olist، ويشمل تنظيف البيانات ومستودع SQL Server وتقرير Power BI من خمس صفحات تفاعلية.
- صمّمت نموذجًا يحافظ على مستوى تفاصيل الطلبات والبنود والمدفوعات والتقييمات، مع 58 مقياس DAX وتعريف واضح لمجتمع كل مؤشر.
- طابقت نتائج SQL وPython باستخدام 3,948 تحققًا، واختبرت التقرير بعد إعادة فتحه عبر 86 حالة DAX و39 مجموعة استعلامات للصفحات.
- حلّلت مبيعات بضائع مؤهلة بقيمة 13.22 مليون ريال برازيلي وسلوك 93,358 هوية عميل، إلى جانب التوصيل وRFM والاحتفاظ حسب الدفعات الشهرية.

## LinkedIn — English

I completed an end-to-end Olist Sales Analytics & Business Intelligence project using Python, SQL Server and Power BI.

The work covers data-quality flags, a warehouse with separate transactional grains, five native interactive report pages, customer/RFM analysis and monthly cohorts. A key challenge was preventing revenue and review duplication while keeping sales, delivery and satisfaction populations explicit.

The accepted snapshot contains R$13.22M in eligible merchandise and 93,358 purchasing identities. The final reopened report passed 86 DAX cases and 39 page-query batches. Findings include a 6.77% late-delivery rate within the valid SLA population and a strong observed association between timeliness and ratings; no causal uplift is inferred.

The repository includes exact KPI/DAX definitions, reproducibility instructions and evidence-backed findings. This is a completed local portfolio project, with service deployment outside its demonstrated scope.

## منشور LinkedIn — العربية

أنهيت مشروع Olist لتحليلات المبيعات وذكاء الأعمال باستخدام Python وSQL Server وPower BI.

المشروع بيغطي فهم البيانات وتنظيفها، وبناء مستودع بيانات، وخمس صفحات تفاعلية للمبيعات والعملاء والتوصيل والتقييمات، مع تحليل RFM والدفعات الشهرية. التحدي الأساسي كان منع تضاعف المبالغ والتقييمات عند الربط، وتحديد مجتمع كل مؤشر بوضوح.

البيانات المؤهلة بتشمل مبيعات بضائع بقيمة 13.22 مليون ريال برازيلي و93,358 هوية عميل. التقرير النهائي اجتاز 86 حالة DAX و39 مجموعة استعلامات بعد حفظه وإعادة فتحه. النتائج وصفية، ومش دليل على سببية أو عائد مالي محقق.

التوثيق بيشمل تعريفات المؤشرات ومعادلات DAX وخطوات إعادة التشغيل وأدلة الاختبار. صور الصفحات جاهزة للعرض ضمن البورتفوليو.

## Interview explanation

**Problem:** Marketplace tables have different grains. Joining items, payments and reviews directly can multiply rows and distort revenue, freight and satisfaction metrics.

**Approach:** Preserve source inputs; add quality flags; aggregate children independently; load a warehouse with explicit facts, dimensions and lineage; build a single-direction semantic model with separate date/geography roles; compare Python, SQL and live DAX results.

**Difficult decisions:** Use `customer_unique_id` for repeat purchasing; distinguish calendar-date SLA from elapsed duration; retain multiple review/order records; explicitly transfer distinct order-category membership; leave future cohort ages missing; return zero only for empty rate numerators with a valid denominator.

**Evidence:** Source contracts and independent assertions support the numbers. Native report save/close/reopen, page export review and representative user-tested interactions support local report acceptance. Different verification methods are documented separately.

**Business value:** The project makes sales contribution, delivery exposure and observed customer behavior measurable with defensible definitions. Proposed actions require further evaluation; profit, causal benefits and production impact are not claimed.

## Presentation assets

Use final native-export previews for a consistent five-page presentation. Use the Delivery/Reviews Desktop captures when illustrating the working application. Earlier three-page captures remain baseline assets. [Dashboard guide](dashboard_guide.md) explains provenance; [business insights](business_insights.md) supplies traceable numbers.
