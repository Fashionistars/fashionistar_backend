










































































# class DashboardStatsAPIView(generics.ListAPIView):
#     serializer_class = SummarySerializer
#     permission_classes = [IsAuthenticated]

#     def get_queryset(self):
#         user = self.request.user
#         try:
#             vendor = fetch_vendor(user)
#             vendor_is_owner(vendor, obj=self.request.user)

#             # Prefetch related data in a single query
#             vendor_products = Product.objects.filter(vendor=vendor).prefetch_related('review_set')
#             paid_orders = CartOrder.objects.filter(vendor=vendor, payment_status="paid")
#             fulfilled_orders = CartOrder.objects.filter(vendor=vendor, payment_status="Fulfilled")
#             cart_order_items = CartOrderItem.objects.filter(vendor=vendor, order__payment_status="paid")

#             product_count = vendor_products.filter(in_stock=False).count()
#             order_count = paid_orders.count()
#             revenue = cart_order_items.aggregate(
#                 total_revenue=Sum(F('sub_total') + F('shipping_amount')))['total_revenue'] or 0
#             review_count = sum(product.review_set.count() for product in vendor_products)
#             average_rating = vendor_products.annotate(avg_rating=Avg('review__rating')).aggregate(
#                 average=Avg('avg_rating'))['average'] or 0
#             average_order_value = fulfilled_orders.aggregate(avg_order_value=Avg('total'))['avg_order_value'] or 0
#             total_sales = paid_orders.aggregate(total_sales=Sum('total'))['total_sales'] or 0
#             user_image = vendor.image.url if vendor.image else ""

#             summary_object = {
#                 'out_of_stock': product_count,
#                 'orders': order_count,
#                 'revenue': revenue,
#                 'review': review_count,
#                 'average_review': average_rating,
#                 'average_order_value': average_order_value,
#                 'total_sales': total_sales,
#                 "user_image": user_image
#             }

#             return [summary_object]

#         except Exception as e:
#             application_logger.exception(f"Error retrieving dashboard stats:")
#             return Response({'error': f'An error occurred, please check your input or contact support. {e}'},
#                             status=status.HTTP_500_INTERNAL_SERVER_ERROR)