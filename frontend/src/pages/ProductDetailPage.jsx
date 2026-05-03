import { useParams, Navigate } from 'react-router-dom'
export default function ProductDetailPage() {
  const { id } = useParams()
  return <Navigate to={`/product/${id}`} replace />
}
