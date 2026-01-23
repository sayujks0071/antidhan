-- Database reconciliation script
-- Checks for duplicate client_order_id and orphan OCO children

-- 1. Check for duplicate client_order_id
SELECT 
    client_order_id,
    COUNT(*) as count,
    array_agg(id ORDER BY id) as order_ids,
    array_agg(status ORDER BY id) as statuses
FROM orders
WHERE client_order_id IS NOT NULL
GROUP BY client_order_id
HAVING COUNT(*) > 1;

-- 2. Check for orphan OCO children (children without parent entry)
SELECT 
    o.id,
    o.client_order_id,
    o.tag,
    o.parent_group,
    o.status
FROM orders o
WHERE o.tag IN ('STOP', 'TP1', 'TP2')
  AND o.parent_group IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 
      FROM orders parent 
      WHERE parent.parent_group = o.parent_group 
        AND parent.tag = 'ENTRY'
  );

-- 3. Check for OCO groups with missing children
SELECT 
    o.parent_group,
    o.tag as entry_tag,
    COUNT(DISTINCT CASE WHEN child.tag IN ('STOP', 'TP1', 'TP2') THEN child.id END) as child_count
FROM orders o
LEFT JOIN orders child ON child.parent_group = o.parent_group AND child.tag IN ('STOP', 'TP1', 'TP2')
WHERE o.tag = 'ENTRY'
  AND o.parent_group IS NOT NULL
  AND o.status = 'FILLED'
GROUP BY o.parent_group, o.tag
HAVING COUNT(DISTINCT CASE WHEN child.tag IN ('STOP', 'TP1', 'TP2') THEN child.id END) = 0;

-- 4. Summary
SELECT 
    'Total orders' as metric,
    COUNT(*)::text as value
FROM orders
UNION ALL
SELECT 
    'Open positions',
    COUNT(*)::text
FROM positions
WHERE status = 'OPEN'
UNION ALL
SELECT 
    'Active orders',
    COUNT(*)::text
FROM orders
WHERE status IN ('PLACED', 'PARTIAL')
UNION ALL
SELECT 
    'Duplicate client_order_ids',
    COUNT(*)::text
FROM (
    SELECT client_order_id
    FROM orders
    WHERE client_order_id IS NOT NULL
    GROUP BY client_order_id
    HAVING COUNT(*) > 1
) dupes;
